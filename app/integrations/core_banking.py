"""
Core-banking REST adapters (C2 - Mambu, Thought Machine Vault, Temenos T24,
Jack Henry Symitar).

Each adapter normalizes the vendor's webhook/API request envelope into the
universal metered analysis request and maps the returned verdict back into the
vendor's response conventions. They are pure transforms (no vendor SDK
dependency) so they run anywhere and are unit-testable offline.

  * Mambu               - POST /v1/transactions payloads (transaction json)
  * Thought Machine Vault - event/command payloads (e.g. postings)
  * Temenos T24         - MWB (message workbench) inbound message envelope
  * Jack Henry Symitar  - credit-union core (Episys/Power1) batch/webhook record
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

logger = logging.getLogger(__name__)


class CoreBankingAdapter(ABC):
    provider: str = "base"

    @abstractmethod
    def to_analysis_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a vendor payload into the universal analysis request."""

    @abstractmethod
    def to_vendor_response(self, verdict: Dict[str, Any]) -> Dict[str, Any]:
        """Map a metered verdict back into the vendor's response shape."""

    def amount_to_float(self, amount: Any) -> float:
        try:
            return float(amount)
        except (TypeError, ValueError):
            return 0.0


class MambuAdapter(CoreBankingAdapter):
    """Mambu core-banking platform (banking-as-a-service)."""

    provider = "mambu"

    def to_analysis_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        txn = payload.get("transaction") or payload
        amount = self.amount_to_float(txn.get("amount") or txn.get("amounts", [{}])[0].get("amount"))
        return {
            "source": "core_banking:mambu",
            "external_id": txn.get("id") or txn.get("creationDate"),
            "amount": amount,
            "currency": txn.get("currency") or (txn.get("amounts") or [{}])[0].get("currency"),
            "debtor": txn.get("senderName") or txn.get("relatedClientId"),
            "creditor": txn.get("receiverName"),
            "type": txn.get("type", "transfer"),
            "is_protected_user": 1 if txn.get("relatedClientId") else 0,
        }

    def to_vendor_response(self, verdict: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "riskScore": verdict.get("risk_score"),
            "decision": verdict.get("decision"),
            "sanctionsBlocked": verdict.get("compliance", {}).get("blocked", False),
            "reasons": verdict.get("compliance", {}).get("reasons", []),
            "zkProofPresent": verdict.get("zk_proof_present"),
        }


class ThoughtMachineVaultAdapter(CoreBankingAdapter):
    """Thought Machine Vault (event-driven core) - posting events."""

    provider = "vault"

    def to_analysis_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event = payload.get("event") or payload.get("payload") or payload
        postings = event.get("postings") or []
        posting = postings[0] if postings else {}
        amount = self.amount_to_float(posting.get("amount"))
        account_id = posting.get("account_id") or event.get("account_id")
        return {
            "source": "core_banking:vault",
            "external_id": posting.get("id") or event.get("event_id"),
            "amount": amount,
            "currency": posting.get("denomination"),
            "debtor": account_id,
            "creditor": None,
            "type": event.get("event_type", "posting"),
            "is_protected_user": 1 if account_id else 0,
        }

    def to_vendor_response(self, verdict: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "risk_score": verdict.get("risk_score"),
            "decision": verdict.get("decision"),
            "blocked": verdict.get("compliance", {}).get("blocked", False),
            "reasons": verdict.get("compliance", {}).get("reasons", []),
        }


class TemenosT24Adapter(CoreBankingAdapter):
    """Temenos Transact (T24) - Message Workbench (MWB) inbound envelope."""

    provider = "temenos_t24"

    def to_analysis_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mwb = payload.get("MWB") or payload.get("message") or payload
        body = mwb.get("body") or mwb.get("record") or mwb
        amount = self.amount_to_float(body.get("AMOUNT") or body.get("amount"))
        return {
            "source": "core_banking:t24",
            "external_id": mwb.get("id") or body.get("TRANSACTION_ID"),
            "amount": amount,
            "currency": body.get("CURRENCY") or body.get("currency"),
            "debtor": body.get("ACCOUNT") or body.get("debtor"),
            "creditor": body.get("CREDIT_ACCOUNT") or body.get("creditor"),
            "type": body.get("TYPE") or "payment",
            "is_protected_user": 1 if (body.get("ACCOUNT") or body.get("debtor")) else 0,
        }

    def to_vendor_response(self, verdict: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "OVERRIDE": verdict.get("decision"),
            "RISK_SCORE": verdict.get("risk_score"),
            "REJECT_REASON": verdict.get("compliance", {}).get("reasons", []),
            "SANCTION_CHECK": "FAILED" if verdict.get("compliance", {}).get("blocked") else "PASSED",
        }


class JackHenrySymitarAdapter(CoreBankingAdapter):
    """Jack Henry Symitar (credit unions) - Episys/Power1 batch record."""

    provider = "jack_henry_symitar"

    def to_analysis_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = payload.get("transaction") or payload.get("record") or payload
        amount = self.amount_to_float(record.get("amount"))
        return {
            "source": "core_banking:symitar",
            "external_id": record.get("transactionId") or record.get("traceNumber"),
            "amount": amount,
            "currency": record.get("currency", "USD"),
            "debtor": record.get("memberNumber") or record.get("fromAccount"),
            "creditor": record.get("toAccount"),
            "type": record.get("type", "transfer"),
            "is_protected_user": 1 if (record.get("memberNumber") or record.get("fromAccount")) else 0,
        }

    def to_vendor_response(self, verdict: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "riskScore": verdict.get("risk_score"),
            "action": verdict.get("decision"),
            "holdRequired": verdict.get("compliance", {}).get("blocked", False),
            "notes": verdict.get("compliance", {}).get("reasons", []),
        }


ADAPTERS: Dict[str, CoreBankingAdapter] = {
    a.provider: a for a in (
        MambuAdapter(), ThoughtMachineVaultAdapter(), TemenosT24Adapter(), JackHenrySymitarAdapter(),
    )
}


def get_adapter(provider: str) -> CoreBankingAdapter:
    adapter = ADAPTERS.get(provider.lower())
    if adapter is None:
        raise ValueError(
            f"unknown core-banking provider '{provider}'; available: {sorted(ADAPTERS)}"
        )
    return adapter
