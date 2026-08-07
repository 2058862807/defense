"""
On-chain usage audit anchor (C1 hybrid metering).

Submits a per-period usage commitment to the deployed UsageAudit registry on
Polygon (chain 137) through the HSM custody signer. Follows the same EIP-1559 +
30 gwei tip conventions as the fairness registry so live Polygon submissions
succeed. Failure is fail-soft at the caller level: the commitment is always
recorded in the local hash-chained ledger first.
"""
import logging
from typing import Optional

from web3 import Web3

from app.core.config import settings
from app.evm.client import EVMClientEnterprise

logger = logging.getLogger(__name__)

USAGE_AUDIT_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "commitment", "type": "bytes32"},
            {"internalType": "uint256", "name": "periodStart", "type": "uint256"},
            {"internalType": "uint256", "name": "eventCount", "type": "uint256"},
            {"internalType": "uint256", "name": "tokensConsumed", "type": "uint256"},
        ],
        "name": "recordPeriod",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "commitment", "type": "bytes32"}],
        "name": "getCommitment",
        "outputs": [
            {
                "components": [
                    {"internalType": "bytes32", "name": "commitment", "type": "bytes32"},
                    {"internalType": "uint256", "name": "periodStart", "type": "uint256"},
                    {"internalType": "uint256", "name": "eventCount", "type": "uint256"},
                    {"internalType": "uint256", "name": "tokensConsumed", "type": "uint256"},
                    {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                    {"internalType": "address", "name": "recorder", "type": "address"},
                ],
                "internalType": "struct UsageAudit.PeriodRecord",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


class UsageAuditAnchor:
    def __init__(self, evm_client: Optional[EVMClientEnterprise] = None, contract_address: Optional[str] = None):
        self.client = evm_client or EVMClientEnterprise()
        self.address = Web3.to_checksum_address(
            contract_address or settings.metering_usage_registry_address
        )
        self.contract = self.client.w3_http.eth.contract(address=self.address, abi=USAGE_AUDIT_ABI)

    def submit(self, period: str, commitment: str, event_count: int, tokens_consumed: int) -> str:
        from datetime import datetime, timezone
        period_start = int(datetime.fromisoformat(period.replace("Z", "+00:00")).timestamp())

        func = self.contract.functions.recordPeriod(
            bytes.fromhex(commitment), period_start, event_count, tokens_consumed
        )
        w3 = self.client.w3_http
        latest = w3.eth.get_block("latest")
        base_fee = latest.get("baseFeePerGas") or w3.eth.gas_price
        priority_fee = Web3.to_wei(30, "gwei")
        max_fee = int(base_fee * 2) + priority_fee

        try:
            gas_estimate = func.estimate_gas({"from": self.client.account.address})
        except Exception as e:
            logger.warning(f"UsageAudit gas estimation failed: {e}")
            gas_estimate = 120000

        tx = {
            "from": self.client.account.address,
            "gas": int(gas_estimate * 1.2),
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
            "nonce": w3.eth.get_transaction_count(self.client.account.address),
            "chainId": settings.evm_chain_id,
        }
        built = func.build_transaction(tx)
        signed = self.client.account.sign_transaction(built)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt.status != 1:
            raise RuntimeError(f"UsageAudit recordPeriod reverted tx={tx_hash.hex()}")
        logger.info(f"UsageAudit anchored commitment={commitment[:16]}... tx={tx_hash.hex()}")
        return tx_hash.hex()


def submit_period_anchor(period: str, commitment: str, event_count: int, tokens_consumed: int) -> str:
    anchor = UsageAuditAnchor()
    return anchor.submit(period, commitment, event_count, tokens_consumed)
