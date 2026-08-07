#!/usr/bin/env python3
"""
Real Sepolia deployment - FairnessRegistry + Groth16Verifier
- Compiles contracts with solc 0.8.20 (py-solc-x)
- Deploys Groth16Verifier (snarkjs-generated) then FairnessRegistry(verifier)
- EIP-1559, chain id 11155111, funded wallet required (Sepolia test ETH)
- Writes artifacts + updates .env with deployed addresses
- On-chain verification step
"""
import json
import logging
import os
import time
from pathlib import Path

import solcx
from web3 import Web3

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
VERIFIER_SOL = ROOT / "contracts" / "verifiers" / "FairnessPolicyVerifier.sol"
REGISTRY_SOL = ROOT / "contracts" / "FairnessRegistry.sol"
OUT_DIR = ROOT / "contracts" / "out"
ARTIFACTS = OUT_DIR / "sepolia_deployment.json"
SOLC_VERSION = "0.8.20"


def compile_all() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    solcx.set_solc_version(SOLC_VERSION)

    def _compile(path: Path) -> dict:
        standard = {
            "language": "Solidity",
            "sources": {path.name: {"content": path.read_text()}},
            "settings": {
                "optimizer": {"enabled": True, "runs": 200},
                "viaIR": True,
                "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}},
            },
        }
        out = solcx.compile_standard(standard, allow_paths=".")
        for contract_name, contract in out["contracts"][path.name].items():
            bytecode = contract["evm"]["bytecode"]["object"]
            return {"abi": contract["abi"], "bin": bytecode}
        raise RuntimeError(f"No contract compiled from {path}")

    artifacts = {
        "FairnessPolicyVerifier": _compile(VERIFIER_SOL),
        "FairnessRegistry": _compile(REGISTRY_SOL),
    }
    for name, out in artifacts.items():
        if not out["bin"]:
            raise RuntimeError(f"Empty bytecode for {name}")
        logger.info(f"Compiled {name}: {len(out['bin']) // 2} bytes bytecode")
    return artifacts


def main():
    if not settings.evm_private_key:
        raise SystemExit("EVM_PRIVATE_KEY not set")

    chain_id = settings.evm_chain_id
    network = {137: "polygon", 1: "ethereum", 11155111: "sepolia"}.get(chain_id, f"chain{chain_id}")

    w3 = Web3(Web3.HTTPProvider(settings.evm_rpc_url.get_secret_value(), request_kwargs={"timeout": 15, "verify": True}))
    from web3.middleware import geth_poa_middleware
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    if not w3.is_connected():
        raise SystemExit("Cannot connect to RPC")
    actual_chain = w3.eth.chain_id
    if actual_chain != chain_id:
        raise SystemExit(f"RPC reports chain {actual_chain}, expected {chain_id}")

    account = w3.eth.account.from_key(settings.evm_private_key.get_secret_value())
    balance = w3.eth.get_balance(account.address)
    logger.info(f"Deployer: {account.address} balance={w3.from_wei(balance, 'ether')} native on {network} (chain {chain_id})")
    if balance == 0:
        raise SystemExit(
            "Deployer has 0 native balance - fund the wallet first "
            f"(send {network} native tokens to {account.address})"
        )

    artifacts = compile_all()

    base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
    priority_fee = 30_000_000_000  # 30 gwei tip - Polygon enforces min 25 gwei
    max_fee = int(base_fee * 2) + priority_fee

    def deploy(name: str, abi: list, bytecode: str, constructor_args=(), gas: int = 3_000_000):
        nonlocal max_fee
        contract = w3.eth.contract(abi=abi, bytecode=bytecode)
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.constructor(*constructor_args).build_transaction({
            "from": account.address,
            "nonce": nonce,
            "chainId": chain_id,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
            "gas": gas,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        logger.info(f"Deploying {name} tx={tx_hash.hex()} ...")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180, poll_latency=2)
        if receipt.status != 1:
            raise RuntimeError(f"{name} deployment reverted")
        addr = receipt["contractAddress"]
        logger.info(f"{name} deployed at {addr} gas_used={receipt['gasUsed']}")
        return addr

    verifier_addr = deploy("Groth16Verifier", artifacts["FairnessPolicyVerifier"]["abi"], artifacts["FairnessPolicyVerifier"]["bin"], gas=1_000_000)
    registry_addr = deploy(
        "FairnessRegistry",
        artifacts["FairnessRegistry"]["abi"],
        artifacts["FairnessRegistry"]["bin"],
        constructor_args=(verifier_addr,),
        gas=2_500_000,
    )

    # On-chain verification of deployment
    registry = w3.eth.contract(address=registry_addr, abi=artifacts["FairnessRegistry"]["abi"])
    owner = registry.functions.owner().call()
    stored_verifier = registry.functions.zkVerifier().call()
    logger.info(f"FairnessRegistry owner={owner} zkVerifier={stored_verifier}")
    assert stored_verifier.lower() == verifier_addr.lower(), "Verifier address mismatch"

    # Real on-chain round-trip: generate a real Groth16 proof and submit it
    # to prove the deployed verifier accepts the production circuit proof.
    if os.environ.get("SKIP_ONCHAIN_SELFTEST") != "1":
        _run_onchain_selftest(w3, account, registry_addr, artifacts["FairnessRegistry"]["abi"], verifier_addr, chain_id)

    deployment = {
        "chain_id": chain_id,
        "network": network,
        "verifier": verifier_addr,
        "fairness_registry": registry_addr,
        "owner": account.address,
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "solc": SOLC_VERSION,
    }
    (OUT_DIR / f"{network}_deployment.json").write_text(json.dumps(deployment, indent=2))
    logger.info(f"Artifacts written to {OUT_DIR / f'{network}_deployment.json'}")

    # Update .env
    env_path = ROOT / ".env"
    env_text = env_path.read_text()
    env_text = _replace_env(env_text, "FAIRNESS_REGISTRY_ADDRESS", registry_addr)
    env_text = _replace_env(env_text, "FAIRNESS_VERIFIER_ADDRESS", verifier_addr)
    env_path.write_text(env_text)
    logger.info("Updated .env FAIRNESS_REGISTRY_ADDRESS / FAIRNESS_VERIFIER_ADDRESS")

    print(json.dumps(deployment, indent=2))
    return deployment


def _run_onchain_selftest(w3, account, registry_addr, registry_abi, verifier_addr, chain_id):
    """Generate a real Groth16 proof, submit it to the deployed registry, and read it back.
    Proves the production circuit + proof encoding + contract ABI all agree on-chain."""
    from app.zk.prover import ZKProverEnterprise
    from app.evm.fairness_registry import FairnessRegistryEnterprise, FAIRNESS_ABI_ENTERPRISE
    from eth_abi import encode as abi_encode

    logger.info("Generating real Groth16 proof for on-chain self-test (17-30s)...")
    prover = ZKProverEnterprise()
    commitments = {
        "model_commitment": "abc123def456abc123def456abc123def456abc123def456abc123def456abcd",
        "input_commitment": "ef7890abcdef7890abcdef7890abcdef7890abcdef7890abcdef7890abcdef78",
    }
    witness = {
        "model_hash": commitments["model_commitment"],
        "features": [[0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 1.0]],
        "slippage_bps": 20,
        "type": "swap",
        "is_protected": 1,
    }
    result = prover.prove(witness, commitments)
    assert result["status"] == "PROVED_REAL_GROTH16", f"selftest proof failed: {result['status']}"
    proof = result["proof"]
    public_inputs = result["public_inputs"]
    logger.info(f"Real proof generated: isFair={public_inputs[0]}")

    # Build the exact encoding the registry client uses
    reg = FairnessRegistryEnterprise(
        contract_address=registry_addr,
        verifier_address=verifier_addr,
    )
    proof_bytes = reg._encode_proof(proof)
    assert proof_bytes and len(proof_bytes) == 256, f"Bad proof encoding: {len(proof_bytes)} bytes"

    model_commitment = reg._format_bytes32(commitments["model_commitment"])
    input_commitment = reg._format_bytes32(commitments["input_commitment"])
    pub = [int(public_inputs[0]), int(public_inputs[1]), int(public_inputs[2])]

    contract = w3.eth.contract(address=registry_addr, abi=registry_abi)
    base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
    max_fee = int(base_fee * 2) + 30_000_000_000
    priority_fee = 30_000_000_000
    func = contract.functions.submitFairnessProof(
        model_commitment, input_commitment, proof_bytes, pub, '{"selftest":true}', False
    )
    try:
        gas = func.estimate_gas({"from": account.address})
    except Exception as e:
        logger.error(f"estimateGas failed during selftest: {e}")
        raise
    tx = func.build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": chain_id,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee,
        "gas": int(gas * 1.2),
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logger.info(f"Selftest submit tx={tx_hash.hex()} ...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180, poll_latency=2)
    if receipt.status != 1:
        raise RuntimeError(f"Selftest submit reverted tx={tx_hash.hex()}")

    # Read back and confirm the verifier accepts it
    record = contract.functions.getRecord(input_commitment).call()
    assert record[8] is True, f"Selftest record not verified: {record}"
    assert contract.functions.verifyProof(input_commitment).call() is True
    logger.info(
        f"SELFTEST PASSED: verified={record[8]} isFair={record[3]} "
        f"submitter={record[6]} publicInputs={list(record[9])}"
    )


def _replace_env(text: str, key: str, value: str) -> str:
    import re
    return re.sub(rf"^{re.escape(key)}=.*$", f"{key}={value}", text, flags=re.MULTILINE)


if __name__ == "__main__":
    main()
