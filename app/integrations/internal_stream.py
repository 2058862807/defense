"""
Internal bank / credit-union transaction stream normalizer (C2).

Adapts the institution's *internal* transaction flow - REST pushes from the
core-banking platform and Kafka messages - into the canonical shape the shared
real-time monitoring pipeline consumes. It reuses the existing vendor adapters
(core-banking, ISO 20022, FIX) so one normalization path serves every
integration the platform already speaks, then applies a small fiat-specific
rule overlay (bank signals the MEV-trained scorer cannot see: channel, missing
purpose, cash-like behaviour) so internal flows are not scored on crypto
features alone.

Normalized output carries the shared pipeline's live-tx fields
(hash/txid, from, to, value_eth=amount, country, timestamp, ...) plus
``is_internal: True`` so the pipeline skips EVM-only steps (mempool intel /
sandwich detection) and applies the rule overlay.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.integrations.core_banking import get_adapter
from app.integrations.iso20022 import ISO20022Adapter
from app.integrations import fix as fix_adapter

logger = logging.getLogger(__name__)

PROVIDERS = {
    "mambu",
    "vault",
    "temenos_t24",
    "jack_henry_symitar",
    "iso20022",
    "fix",
    "universal",
}

# Fiat channel types with elevated money-laundering / fraud exposure.
CASH_LIKE_CHANNELS = {"atm", "cash", "cdm", "cheque", "check", "teller", "wire"}
# Payment purposes commonly associated with sanctions / ML risk.
HIGH_RISK_PURPOSES = {
    "gambling", "casino", "crypto", "cryptocurrency", "sanctions",
    "weapons", "drug", "money-laundering", "smuggling",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _content_hash(item: Dict[str, Any], source: str) -> str:
    """Deterministic tx id so duplicate stream deliveries collapse to one ledger entry."""
    canon = json.dumps(item, sort_keys=True, default=str)
    digest = hashlib.sha256(canon.encode()).hexdigest()
    return f"int-{source}-{digest[:40]}" if source else f"int-{digest[:40]}"


def _rule_overlay(item: Dict[str, Any], amount: float, currency: str) -> Dict[str, Any]:
    """Fiat-specific rule signals the crypto scorer cannot see.

    Returns {"rule_risk_bonus": 0-20, "risk_signals": [...]}. Bonus is added to
    the ML score by the shared pipeline only for internal transactions, leaving
    the mempool score untouched.
    """
    signals: List[str] = []
    bonus = 0.0

    channel = str(item.get("channel") or "").strip().lower()
    if channel in CASH_LIKE_CHANNELS:
        signals.append(f"cash-like channel ({channel})")
        bonus += 8.0

    purpose = str(item.get("purpose") or "").strip().lower()
    if purpose in HIGH_RISK_PURPOSES:
        signals.append(f"high-risk purpose ({purpose})")
        bonus += 8.0
    elif not purpose:
        signals.append("missing payment purpose")
        bonus += 3.0

    country = str(item.get("country") or "").strip().upper()
    if country and country not in ("US", "USA"):
        signals.append(f"cross-border ({country})")
        bonus += 5.0

    large = settings.internal_rule_large_amount_usd
    if amount >= large:
        signals.append(f"large internal value (>= ${large:,.0f})")
        bonus += 10.0

    return {"rule_risk_bonus": min(round(bonus, 1), 20.0), "risk_signals": signals}


class InternalTxNormalizer:
    """Normalizes raw internal-transaction payloads into live-pipeline tx dicts."""

    def __init__(self):
        self._iso = ISO20022Adapter()

    # ------------------------------------------------------------------ #
    def normalize_batch(self, payload: Any) -> List[Dict[str, Any]]:
        """Normalize a push payload into per-transaction results.

        Each result is {"ok": bool, "tx": dict | None, "error": str | None,
        "ref": str}. Invalid items are isolated - one bad record never rejects
        the whole batch.
        """
        results: List[Dict[str, Any]] = []
        default_provider = None
        items: List[Any] = []

        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            default_provider = str(payload.get("provider") or "").strip() or None
            fmt = str(payload.get("format") or "").strip().lower() or None
            if fmt == "iso20022":
                default_provider = "iso20022"
            elif fmt == "fix":
                default_provider = "fix"
            if isinstance(payload.get("transactions"), list):
                items = payload["transactions"]
            elif isinstance(payload.get("entries"), list):
                items = [{"account": payload.get("account"), **e}
                         for e in payload["entries"]]
            elif payload.get("message"):
                items = [payload]
            elif any(k in payload for k in ("amount", "debit_credit", "message_family")):
                items = [payload]
            elif default_provider and any(
                k in payload for k in ("transaction", "record", "MWB", "event", "postings")
            ):
                # Provider-scoped single-transaction push (vendor envelope).
                items = [payload]
            else:
                raise ValueError("no internal transactions found in payload")
        else:
            raise ValueError("payload must be a JSON object or array")

        if len(items) > settings.internal_tx_batch_limit:
            raise ValueError(
                f"batch exceeds limit ({len(items)} > {settings.internal_tx_batch_limit})"
            )

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                results.append({"ok": False, "tx": None, "error": "item is not a JSON object", "ref": f"#{idx}"})
                continue
            provider = str(item.get("provider") or "").strip() or default_provider
            fmt = str(item.get("format") or "").strip().lower()
            try:
                tx = self.normalize_item(item, provider=provider, _format=fmt)
                results.append({"ok": True, "tx": tx, "error": None,
                                "ref": tx.get("external_id") or tx.get("hash")})
            except Exception as e:
                logger.warning(f"Internal-tx item #{idx} rejected: {e}")
                results.append({
                    "ok": False, "tx": None,
                    "error": str(e),
                    "ref": item.get("external_id") or item.get("id") or f"#{idx}",
                })
        return results

    # ------------------------------------------------------------------ #
    def normalize_item(self, item: Dict[str, Any], provider: Optional[str] = None,
                       _format: Optional[str] = None) -> Dict[str, Any]:
        provider = (provider or str(item.get("provider") or "")).strip() or "universal"
        provider = provider.lower()
        _format = (_format or str(item.get("format") or "")).strip().lower()

        if provider == "iso20022" or _format == "iso20022" or "message_family" in item:
            return self._normalize_iso20022(item)
        if provider == "fix" or _format == "fix":
            return self._from_universal(fix_adapter.to_analysis_request(item), source="fix", raw=item)
        if provider in ("mambu", "vault", "temenos_t24", "jack_henry_symitar"):
            req = get_adapter(provider).to_analysis_request(item)
            return self._from_universal(req, source=f"core_banking:{provider}", raw=item)
        if provider not in ("universal", ""):
            raise ValueError(
                f"unknown provider '{provider}'; available: {sorted(PROVIDERS)}"
            )
        return self._from_universal(item, source="universal", raw=item)

    # ------------------------------------------------------------------ #
    def _normalize_iso20022(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if "message" in item and isinstance(item["message"], str):
            parsed = self._iso.parse(item["message"])
        elif "message_family" in item or "transactions" in item or "entries" in item:
            parsed = item
        else:
            raise ValueError("iso20022 item must carry a 'message' XML string or parsed payload")
        family = parsed.get("message_family", "pacs.008")
        entries = parsed.get("transactions") or parsed.get("entries") or []
        if not entries:
            # Single-message payment without per-tx entries.
            req = self._iso.to_analysis_request(parsed)
            req.setdefault("external_id", parsed.get("message_id"))
            return self._from_universal(req, source="iso20022", raw=parsed)
        if family.startswith(("pacs", "pain")):
            first = entries[0]
            # Multiple CdtTrfTxInf in one message: expose the first as the tx
            # and attach the rest as related transactions for downstream alerting.
            tx = self._from_universal(first, source="iso20022", raw=parsed,
                                      base_id=parsed.get("message_id"))
            tx["uetr"] = parsed.get("uetr")
            tx["message_family"] = family
            return tx
        # camt reports: expand first entry; the batch path expands each entry.
        return self._from_universal(entries[0], source="iso20022:report", raw=parsed,
                                    base_id=parsed.get("message_id"))

    # ------------------------------------------------------------------ #
    def _from_universal(self, req: Dict[str, Any], source: str, raw: Any,
                        base_id: Optional[str] = None) -> Dict[str, Any]:
        amount = abs(_as_float(req.get("amount")))
        currency = str(req.get("currency") or "USD").upper()
        external_id = str(req.get("external_id")
                          or req.get("message_id")
                          or req.get("end_to_end_id")
                          or base_id or "").strip()

        from_party = req.get("debtor") or req.get("from_account") or req.get("from")
        to_party = req.get("creditor") or req.get("to_account") or req.get("to")
        if not from_party or not to_party:
            # camt-style report entries: counterparty is the other side, the
            # account under review is the internal one.
            deb = str(req.get("debit_credit") or "").upper()
            raw_account = raw.get("account") if isinstance(raw, dict) else None
            if req.get("counterparty"):
                if deb == "DBIT":
                    from_party = req.get("account") or raw_account or from_party
                    to_party = req.get("counterparty")
                elif deb == "CRDT":
                    from_party = req.get("counterparty")
                    to_party = req.get("account") or raw_account or to_party

        country = str(req.get("country") or "").strip()
        if not country:
            country = str(req.get("debtor_country") or "").strip()
        if not country and currency not in ("USD", "US"):
            country = "US"

        type_ = str(req.get("type") or "transfer").lower()
        channel = str(req.get("channel") or raw.get("channel") or "").strip()

        overlay = _rule_overlay(req, amount, currency)
        tx_hash = external_id or _content_hash({**req, "source": source}, source)

        tx: Dict[str, Any] = {
            "source": f"internal:{source}",
            "is_internal": True,
            "hash": tx_hash,
            "txid": tx_hash,
            "external_id": external_id or tx_hash,
            "from": from_party,
            "to": to_party,
            "user": req.get("debtor") or req.get("user") or "",
            "country": country,
            "type": type_,
            "channel": channel,
            "purpose": req.get("purpose") or raw.get("purpose"),
            "to_chain": "FIAT",
            "currency": currency,
            "amount": amount,
            "value_eth": amount,
            "gas_price_gwei": 0,
            "slippage_bps": 0,
            "pool_liquidity_eth": 1000,
            "tx_count_in_block": 1,
            "is_router": 0,
            "is_protected_user": 1,
            "timestamp": req.get("timestamp") or req.get("booked_date")
                         or req.get("created") or _utcnow(),
            "rule_risk_bonus": overlay["rule_risk_bonus"],
            "risk_signals": overlay["risk_signals"],
            "parties": req.get("parties", []),
            "raw": raw,
        }
        if req.get("uetr"):
            tx["uetr"] = req["uetr"]
        if req.get("account"):
            tx["account"] = req["account"]
        return tx


normalizer = InternalTxNormalizer()
