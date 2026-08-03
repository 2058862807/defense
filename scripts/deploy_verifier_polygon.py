#!/usr/bin/env python3
"""
Deploy the Groth16 fairness verifier to Polygon mainnet (chain 137) and wire it.

Steps (each gated on the previous succeeding):
1. Compile contracts/verifiers/FairnessPolicyVerifier.sol with solc 0.8.20
   (source is regenerable via `snarkjs zkey export solidityverifier`; the file
   is verified to match circuits/build/fairness_policy_final.zkey).
2. Generate a REAL Groth16 proof for a policy-compliant arbitrage witness via
   the local snarkjs ingestor (the same path the pilot uses).
3. Deploy the verifier through the custody signer (EIP-1559, chain 137).
4. eth_call verifyProof on-chain with the real proof - MUST return true,
   otherwise the deploy is treated as failed (no wiring happens).
5. Repoint the FairnessRegistry (owner = our signer) to the new verifier via
   setVerifier(newVerifier).
6. Update .env FAIRNESS_VERIFIER_ADDRESS and save a deployment artifact.

Cost is negligible (~0.1-0.2 MATIC). Run:
    venv/bin/python scripts/deploy_verifier_polygon.py
"""
import json
import logging
import sys
import time
from pathlib import Path

import solcx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from app.core.config import settings
from app.evm.client import EVMClientEnterprise
from app.ml.scorer import ProteanScorerEnterprise
from app.zk.prover import ZKProverEnterprise
from app.zk.verifier import GROTH16_VERIFIER_ABI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deploy_verifier_polygon")

VERIFIER_SOL = Path("contracts/verifiers/FairnessPolicyVerifier.sol")
SOLC_VERSION = "0.8.20"

SET_VERIFIER_ABI = [{
    "inputs": [{"internalType": "address", "name": "_verifier", "type": "address"}],
    "name": "setVerifier", "outputs": [], "stateMutability": "nonpayable", "type": "function",
}]


def compile_verifier() -> dict:
    out = solcx.compile_source(
        VERIFIER_SOL.read_text(), solc_version=SOLC_VERSION,
        output_values=["abi", "bin"], optimize=True,
    )
    name = [k for k in out if k.endswith("Groth16Verifier")][0]
    return {"abi": out[name]["abi"], "bin": out[name]["bin"]}


def generate_real_proof():
    scorer = ProteanScorerEnterprise()
    tx = {"type": "arbitrage", "value_eth": 2.0, "gas_price_gwei": 30,
          "slippage_bps": 20, "pool_liquidity_eth": 1000, "is_protected_user": 0}
    score, meta = scorer.score(tx)
    witness = {
        "model_hash": meta["model_hash"], "features": meta["features"],
        "score": score, "policy": settings.fairness_policy, "type": "arbitrage",
        "slippage_bps": 20, "value_eth": 2.0, "is_protected_user": 0,
    }
    commitments = {"model_commitment": meta["model_hash"], "input_commitment": "ab" * 32}
    result = ZKProverEnterprise().prove(witness, commitments)
    if result["status"] != "PROVED_REAL_GROTH16":
        raise RuntimeError("real proof generation failed")
    logger.info(f"real proof generated: public_inputs={[str(p)[:10] for p in result['public_inputs']]}")
    return result


def verify_onchain(w3, address, result) -> bool:
    c = w3.eth.contract(address=Web3.to_checksum_address(address), abi=GROTH16_VERIFIER_ABI)
    pf = result["proof"]
    a = [int(pf["pi_a"][0]), int(pf["pi_a"][1])]
    # snarkjs G2 rows are (imag, real); the contract expects (real, imag).
    b = [[int(pf["pi_b"][0][1]), int(pf["pi_b"][0][0])],
         [int(pf["pi_b"][1][1]), int(pf["pi_b"][1][0])]]
    cpt = [int(pf["pi_c"][0]), int(pf["pi_c"][1])]
    inp = [int(p) for p in result["public_inputs"]]
    return bool(c.functions.verifyProof(a, b, cpt, inp).call())


def main():
    evm = EVMClientEnterprise()
    w3 = evm.w3_http
    assert w3.eth.chain_id == 137, f"must run on Polygon mainnet, got {w3.eth.chain_id}"
    if not evm.account:
        raise RuntimeError("no custody signer available")
    logger.info(f"chainId=137 signer={evm.account.address} balance={w3.eth.get_balance(evm.account.address)/1e18:.3f} MATIC")

    verifier = compile_verifier()
    logger.info(f"verifier compiled: bytecode={len(verifier['bin'])//2} bytes")
    result = generate_real_proof()

    contract = w3.eth.contract(abi=verifier["abi"], bytecode=verifier["bin"])
    gas = contract.constructor().estimate_gas({"from": evm.account.address})
    fee = w3.eth.fee_history(3, "latest", [80])
    base = fee["baseFeePerGas"][-1]
    max_priority = w3.to_wei(30, "gwei")  # Polygon requires >= 25 gwei tip
    tx = contract.constructor().build_transaction({
        "from": evm.account.address,
        "gas": int(gas * 1.3),
        "maxFeePerGas": int(base * 2 + max_priority),
        "maxPriorityFeePerGas": max_priority,
        "nonce": w3.eth.get_transaction_count(evm.account.address),
        "chainId": 137,
    })
    logger.info(f"deploying verifier: gas={tx['gas']} cost_est={tx['gas']*tx['maxFeePerGas']/1e18:.4f} MATIC")
    tx_hash = evm.send_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    if receipt.status != 1:
        raise RuntimeError(f"verifier deployment reverted tx={tx_hash.hex()}")
    verifier_address = receipt.contractAddress
    logger.info(f"verifier deployed at {verifier_address} tx={tx_hash} gasUsed={receipt.gasUsed}")

    if not verify_onchain(w3, verifier_address, result):
        raise RuntimeError("on-chain verifyProof FAILED for a snarkjs-verified proof - deployment rejected")
    logger.info("ON-CHAIN verifyProof(real proof) = True  (crown-jewel check passed)")

    # Repoint the registry to the new verifier (owner is our signer).
    registry = w3.eth.contract(address=Web3.to_checksum_address(settings.fairness_registry_address), abi=SET_VERIFIER_ABI)
    set_tx = registry.functions.setVerifier(Web3.to_checksum_address(verifier_address)).build_transaction({
        "from": evm.account.address,
        "gas": 80000,
        "maxFeePerGas": int(base * 2 + max_priority),
        "maxPriorityFeePerGas": max_priority,
        "nonce": w3.eth.get_transaction_count(evm.account.address),
        "chainId": 137,
    })
    set_hash = evm.send_transaction(set_tx)
    set_receipt = w3.eth.wait_for_transaction_receipt(set_hash, timeout=300)
    if set_receipt.status != 1:
        raise RuntimeError("registry.setVerifier reverted")
    logger.info(f"registry repointed to new verifier tx={set_hash.hex()}")

    # Update .env
    env_path = Path(".env")
    text = env_path.read_text()
    old_line = next((l for l in text.splitlines() if l.startswith("FAIRNESS_VERIFIER_ADDRESS=")), None)
    if old_line is None:
        raise RuntimeError("FAIRNESS_VERIFIER_ADDRESS not found in .env")
    text = text.replace(old_line, f"FAIRNESS_VERIFIER_ADDRESS={verifier_address}")
    env_path.write_text(text)
    logger.info(f".env updated: FAIRNESS_VERIFIER_ADDRESS={verifier_address}")

    artifact = {
        "verifier_address": verifier_address,
        "deploy_tx": tx_hash.hex(),
        "set_verifier_tx": set_hash.hex(),
        "deployer": evm.account.address,
        "chain_id": 137,
        "circuit_hash": settings.zk_circuit_hash,
        "policy_version": settings.fairness_policy_version,
        "verified_onchain": True,
        "timestamp": time.time(),
    }
    out = Path(f"deployments/polygon_verifier_{time.strftime('%Y%m%d_%H%M%S')}.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n")
    logger.info(f"artifact saved: {out}")
    print(json.dumps(artifact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
