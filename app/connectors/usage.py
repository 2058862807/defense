"""
Usage Tracking - Enterprise (metering-backed)
GAP8: Complete usage tracking

- Tracks API usage per API key, grant, customer - persisted in the durable
  metering ledger (data/metering.db, SQLite WAL + optional Postgres mirror).
- Metrics: total requests, success/error, per-endpoint breakdown.
- Tier limits are retired: entitlement is enforced by the grant's fixed token
  pool (see app/metering/migrate.ensure_grant_for_license). These helpers keep
  the legacy public API for the connector / licensing server while delegating
  all state to the metering store.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

from app.metering.store import (
    EntitlementError,
    MeteringStore,
    metering_store as _default_store,
)
from app.metering.migrate import grant_for_key

logger = logging.getLogger(__name__)


def _decision_for(status: int) -> Optional[str]:
    return None if status is None else ("pass" if status < 400 else "error")


def record_usage(
    api_key: str,
    endpoint: str,
    latency_ms: float,
    status: int,
    customer: Optional[str] = None,
    store: Optional[MeteringStore] = None,
) -> Dict:
    """
    Record API usage - called by connector and API services.

    Writes a zero-token audit event to the metering ledger (no double-charge:
    the request's token was already settled by the metered dependency). Returns
    a compat-shaped record or an empty one for unknown keys.
    """
    store = store or _default_store
    grant = grant_for_key(api_key, store=store)
    if not grant:
        logger.warning(f"Usage recorded for unknown API key: {api_key[:20]}...")
        return {"api_key": api_key[:20] + "...", "endpoint": endpoint, "status": status, "recorded": False}

    try:
        res = store.authorize_reservation(api_key, endpoint=endpoint, tokens=0)
        store.settle_reservation(
            res["reservation_id"],
            event_type="api_call",
            decision=_decision_for(status),
            score=None,
        )
        recorded = True
    except EntitlementError as e:
        logger.warning(f"Usage record skipped for {api_key[:20]}...: {e}")
        return {"api_key": api_key[:20] + "...", "endpoint": endpoint, "status": status, "recorded": False}

    return {
        "api_key": api_key[:20] + "...",
        "customer": customer or grant["customer_id"],
        "endpoint": endpoint,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": latency_ms,
        "status": status,
        "recorded": recorded,
    }


def get_usage_stats(
    api_key: Optional[str] = None,
    customer: Optional[str] = None,
    days: int = 7,
    store: Optional[MeteringStore] = None,
) -> Dict:
    """
    Get usage stats - for customer portal and tiered disclosure.

    Aggregates usage_events from the metering store into the legacy shape.
    Latency is not persisted by the ledger; avg/p95 return 0.
    """
    store = store or _default_store
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).isoformat()

    events: List[Dict] = []
    if customer:
        for grant in store.list_grants(customer_id=customer):
            events.extend(store.usage_for_grant(grant["id"], since=cutoff, limit=10000))
    elif api_key:
        grant = grant_for_key(api_key, store=store)
        events = store.usage_for_grant(grant["id"], since=cutoff, limit=10000) if grant else []
    else:
        events = store.all_usage(since=cutoff, limit=10000)

    total = len(events)
    success = len([e for e in events if e.get("decision") not in (None, "error")])
    error = total - success

    per_endpoint = defaultdict(int)
    for e in events:
        per_endpoint[e.get("endpoint") or "unknown"] += 1

    return {
        "total_requests": total,
        "success": success,
        "error": error,
        "success_rate": success / total if total > 0 else 0,
        "error_rate": error / total if total > 0 else 0,
        "avg_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
        "per_endpoint": dict(per_endpoint),
        "period_days": days,
        "period_start": cutoff,
        "period_end": now.isoformat(),
    }


def get_customer_usage(customer: str, days: int = 30, store: Optional[MeteringStore] = None) -> Dict:
    """Get usage for customer across all their grants."""
    store = store or _default_store
    customer_row = store.get_customer_by_name(customer)
    grants = store.list_grants(customer_id=customer_row["id"]) if customer_row else []

    total = 0
    pool = 0
    consumed = 0
    tier = "dev"
    for grant in grants:
        total += store.grant_balance(grant["id"]).get("tokens_consumed", 0)
        pool += grant["token_pool"]
        consumed += grant["tokens_consumed"]
        tier = grant["tier"] or tier

    remaining = max(0, pool - consumed)
    usage_percent = (consumed / pool * 100) if pool > 0 else 0

    return {
        "customer": customer,
        "tier": tier,
        "period_days": days,
        "total_requests": total,
        "grants": len(grants),
        "token_pool": pool,
        "tokens_consumed": consumed,
        "tokens_remaining": remaining,
        "limit_period": pool,
        "usage_percent": usage_percent,
        "remaining": remaining,
        "stats": get_usage_stats(customer=customer, days=days, store=store),
    }


def check_rate_limit(api_key: str, store: Optional[MeteringStore] = None) -> bool:
    """
    Check if API key is within its token entitlement.

    Reserves and immediately releases one token; returns True when the grant is
    active and funded, False when the key is unknown/expired/exhausted.
    """
    store = store or _default_store
    if not store.verify_api_key(api_key):
        return False
    try:
        res = store.authorize_reservation(api_key, endpoint="/rate-limit-check", tokens=1)
        store.release_reservation(res["reservation_id"])
        return True
    except EntitlementError:
        return False
