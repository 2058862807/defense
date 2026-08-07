#!/usr/bin/env python3
"""
Deploy the UsageAudit registry to Polygon mainnet (chain 137) and wire it.

The UsageAudit contract stores per-period metering commitments (SHA-256 over
usage events + grant balances) so a pilot's token consumption can be audited
on-chain. It is a small, owner-only append-only registry.

Steps:
1. Compile contracts/UsageAudit.sol with solc 0.8.20.
2. Deploy through the custody signer (EIP-1559, 30 gwei tip, chain 137).
3. eth_call recordPeriod (simulate) to prove the contract is callable.
4. Update .env METERING_USAGE_REGISTRY_ADDRESS and save a deployment artifact.

Cost is negligible (< 0.01 MATIC). Run:
    venv/bin/python scripts/deploy_usage_audit.py
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deploy_usage_audit")

SOL_PATH = Path("contracts/UsageAudit.sol")
SOLC_VERSION = "0.8.20"

USAGE_AUDIT_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "commitment", "type": "bytes32"},
            {"internalType": "uint256", "name": "periodStart", "type": "uint256"},
            {"internalType": "uint256", "name": "eventCount", "type": "uint256"},
            {"internalType": "uint256", "name": "tokensConsumed", "type": "uint256"},
        ],
        "name": "recordPeriod", "outputs": [], "stateMutability": "nonpayable", "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "commitment", "type": "bytes32"}],
        "name": "getCommitment", "outputs": [
            {
                "components": [
                    {"internalType": "bytes32", "name": "commitment", "type": "bytes32"},
                    {"internalType": "uint256", "name": "periodStart", "type": "uint256"},
                    {"internalType": "uint256", "name": "eventCount", "type": "uint256"},
                    {"internalType": "uint256", "name": "tokensConsumed", "type": "uint256"},
                    {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                    {"internalType": "address", "name": "recorder", "type": "address"},
                ],
                "internalType": "struct UsageAudit.PeriodRecord", "name": "", "type": "tuple",
            }
        ],
        "stateMutability": "view", "type": "function",
    },
]


def compile_usage_audit() -> dict:
    out = solcx.compile_source(
        SOL_PATH.read_text(), solc_version=SOLC_VERSION,
        output_values=["abi", "bin"], optimize=True,
    )
    name = [k for k in out if k.endswith("UsageAudit")][0]
    return {"abi": out[name]["abi"], "bin": out[name]["bin"]}


def main():
    evm = EVMClientEnterprise()
    w3 = evm.w3_http
    assert w3.eth.chain_id == 137, f"must run on Polygon mainnet, got {w3.eth.chain_id}"
    if not evm.account:
        raise RuntimeError("no custody signer available")
    logger.info(f"chainId=137 signer={evm.account.address} balance={w3.eth.get_balance(evm.account.address)/1e18:.3f} MATIC")

    compiled = compile_usage_audit()
    logger.info(f"UsageAudit compiled: bytecode={len(compiled['bin'])//2} bytes")

    contract = w3.eth.contract(abi=compiled["abi"], bytecode=compiled["bin"])
    gas = contract.constructor().estimate_gas({"from": evm.account.address})
    fee = w3.eth.fee_history(3, "latest", [80])
    base = fee["baseFeePerGas"][-1]
    max_priority = w3.to_wei(30, "gwei")
    tx = contract.constructor().build_transaction({
        "from": evm.account.address,
        "gas": int(gas * 1.3),
        "maxFeePerGas": int(base * 2 + max_priority),
        "maxPriorityFeePerGas": max_priority,
        "nonce": w3.eth.get_transaction_count(evm.account.address),
        "chainId": 137,
    })
    logger.info(f"deploying UsageAudit: gas={tx['gas']} cost_est={tx['gas']*tx['maxFeePerGas']/1e18:.6f} MATIC")
    tx_hash = evm.send_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    if receipt.status != 1:
        raise RuntimeError(f"UsageAudit deployment reverted tx={tx_hash}")
    address = receipt.contractAddress
    logger.info(f"UsageAudit deployed at {address} tx={tx_hash} gasUsed={receipt.gasUsed}")

    # Simulate recordPeriod via eth_call to prove the contract accepts anchors.
    c = w3.eth.contract(address=Web3.to_checksum_address(address), abi=USAGE_AUDIT_ABI)
    sim = c.functions.recordPeriod(b"\x11" * 32, 1700000000, 1, 1).call({"from": evm.account.address})
    logger.info(f"recordPeriod simulation ok (gas-validated): {sim}")

    env_path = Path(".env")
    text = env_path.read_text()
    key = "METERING_USAGE_REGISTRY_ADDRESS"
    if key in text:
        lines = [l for l in text.splitlines() if not l.startswith(f"{key}=")]
        text = "\n".join(lines + [f"{key}={address}"]) + "\n"
    else:
        text = text.rstrip("\n") + f"\n{key}={address}\n"
    env_path.write_text(text)
    logger.info(f".env updated: {key}={address}")

    artifact = {
        "usage_audit_address": address,
        "deploy_tx": tx_hash,
        "deployer": evm.account.address,
        "chain_id": 137,
        "abi": USAGE_AUDIT_ABI,
        "timestamp": time.time(),
    }
    out = Path(f"deployments/polygon_usage_audit_{time.strftime('%Y%m%d_%H%M%S')}.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n")
    logger.info(f"artifact saved: {out}")
    print(json.dumps({k: v for k, v in artifact.items() if k != "abi"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
