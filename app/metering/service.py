"""
High-level metering / token-licensing service (C1).

Implements the pilot-to-paid product protection model:

  * A pilot customer is issued a fixed token pool valid for 6 months.
  * One token = one full transaction analysis. Consumption is atomic.
  * When the pool is exhausted (or the grant expires) every metered API call
    returns 402 Payment Required with a license offer.
  * The customer may purchase a license (payment webhook) to top up / convert,
    or let the pilot lapse.

On-chain audit (hybrid): a per-period commitment over usage is appended to the
durable hash-chained ledger (always) and, when a UsageAudit registry address is
configured, submitted to Polygon.
"""
import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import audit_log

from app.metering.store import MeteringStore, EntitlementError

logger = logging.getLogger(__name__)


def license_offer(grant: Optional[Dict[str, Any]], reason: str = "out_of_tokens") -> Dict[str, Any]:
    """Build the payment offer returned with a 402 response."""
    price_cents = settings.metering_license_price_usd_cents
    return {
        "reason": reason,
        "offer": "paid_license",
        "price": {
            "amount_cents": price_cents,
            "currency": settings.metering_license_display_currency,
            "label": f"License tier upgrade (includes top-up tokens)",
        },
        "grant_id": (grant or {}).get("id"),
        "purchase_endpoint": "/metering/grants/{grant_id}/purchase",
        "payment_webhook": "/metering/payments/webhook",
        "message": "Your pilot token supply is exhausted. Purchase a license to continue, or let the pilot lapse.",
    }


def create_purchase_token(grant_id: str) -> Dict[str, Any]:
    """One-time opaque purchase token that the payment provider echoes back."""
    return {
        "purchase_token": f"pt_{secrets.token_hex(16)}",
        "grant_id": grant_id,
        "amount_cents": settings.metering_license_price_usd_cents,
        "currency": settings.metering_license_display_currency,
        "expires_in_seconds": 3600,
    }


def period_start(period: Optional[str] = None, days: Optional[int] = None) -> str:
    """ISO timestamp marking the start of the current audit period."""
    from datetime import timedelta
    days = days or settings.metering_audit_period_days
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=days)).isoformat()


def expiry_iso(months: int) -> str:
    """Expiry timestamp for a fixed-pool pilot grant (months from now)."""
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(days=months * 30)).isoformat()


def period_commitment(store: MeteringStore, since: str) -> Dict[str, Any]:
    """Deterministic commitment over a period's usage + grant balances.

    The commitment is the SHA-256 of the canonical JSON of every usage event in
    the period plus the remaining balances of every grant, so an on-chain
    anchor can be re-derived and cross-checked by an auditor.
    """
    events = store.period_usage(since)
    grants = store.list_grants()
    balances = [store.grant_balance(g["id"]) for g in grants]
    canonical = json.dumps(
        {"since": since, "events": events, "balances": balances},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return {
        "period": since,
        "event_count": len(events),
        "tokens_consumed_total": sum(e["tokens"] for e in events),
        "commitment": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "canonical_len": len(canonical),
    }


def anchor_period(store: MeteringStore, since: Optional[str] = None, ledger=None) -> Dict[str, Any]:
    """Record the period commitment in the tamper-evident ledger (always) and,
    when configured, submit it to the Polygon UsageAudit registry (optional)."""
    since = since or period_start()
    commit = period_commitment(store, since)
    result = {"commitment": commit, "onchain": {"submitted": False, "tx_hash": None, "reason": None}}

    # 1) Always: append to the durable hash-chained ledger.
    if ledger is not None:
        entry = ledger.append(
            event_type="METERING_PERIOD_AUDIT",
            payload={
                "period": since,
                "commitment": commit["commitment"],
                "event_count": commit["event_count"],
                "tokens_consumed_total": commit["tokens_consumed_total"],
            },
            status="committed",
        )
        result["ledger_entry_hash"] = entry["entry_hash"]
    else:
        result["ledger_entry_hash"] = None

    # 2) Optional: on-chain anchor via the UsageAudit registry.
    if settings.metering_usage_registry_address:
        try:
            from app.metering.usage_anchor import submit_period_anchor
            tx_hash = submit_period_anchor(
                period=since,
                commitment=commit["commitment"],
                event_count=commit["event_count"],
                tokens_consumed=commit["tokens_consumed_total"],
            )
            result["onchain"] = {"submitted": True, "tx_hash": tx_hash}
            audit_log(
                "METERING_ANCHORED", "metering", "anchor", since, "SUCCESS",
                {"commitment": commit["commitment"], "tx_hash": tx_hash},
            )
        except Exception as e:
            result["onchain"]["reason"] = str(e)
            logger.error(f"Metering on-chain anchor failed (commitment still recorded locally): {e}")
    else:
        result["onchain"]["reason"] = "metering_usage_registry_address not configured"

    return result
