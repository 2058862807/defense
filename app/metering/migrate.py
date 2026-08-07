"""
Migration bridge - legacy license files / connector surfaces over the metering store.

The demo-era licensing stack (app/licensing/*, app/connectors/usage.py) kept
entitlement state in in-memory dicts. This module lets those surfaces keep
working while the *real* state lives in the durable metering ledger:

  * ensure_grant_for_license - idempotently maps a signed license file (tier +
    features + expiry) to a fixed metering grant, keyed by license_id in the
    grant's purchase_order column.
  * metered_authorize - the token-billing check the enterprise connector now
    uses instead of the license-file verifier: API key -> grant -> feature
    permission -> atomic token reservation.
  * get_connector_qps - informational QPS for the connector middleware;
    real enforcement is the token reservation.

The signed license file remains the crypto artifact (ECDSA P-256); the grant is
the billing/entitlement source of truth.
"""
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import settings
from app.metering.store import (
    EntitlementError,
    MeteringStore,
    NoEntitlementError,
    metering_store as _default_store,
)

logger = logging.getLogger(__name__)

# Legacy tier limits are retired: a license's allowance is now its fixed token
# pool, derived from its daily tx allowance x remaining term. Used only for
# display/derivation below.
_TIER_LIMITS = {"dev": 1000, "enterprise": 10000, "enterprise_gov": 100000}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def tokens_for_license(license_data: Dict[str, Any]) -> int:
    """Derive the fixed token pool for a license from its defense allowance.

    pool = max_protected_txs_per_day * remaining_days (min 1 day). Falls back
    to the legacy tier limit for a day when the feature is absent, and clamps
    to a sane ceiling so a bad file cannot mint an unbounded pool.
    """
    features = license_data.get("features", {}) or {}
    defense = features.get("defense", {}) or {}
    per_day = int(defense.get("max_protected_txs_per_day") or _TIER_LIMITS.get(license_data.get("tier"), 1000))
    try:
        remaining = _parse_iso(license_data["expiry"]) - datetime.now(timezone.utc)
        days_left = max(1, math.ceil(remaining.total_seconds() / 86400))
    except (KeyError, ValueError, TypeError):
        days_left = 1
    return min(per_day * days_left, 1_000_000_000)


def _license_expiry(license_data: Dict[str, Any]) -> str:
    raw = license_data.get("expiry")
    if not raw:
        raise EntitlementError("license missing expiry", license_data)
    return raw.replace("Z", "+00:00")


def ensure_grant_for_license(
    license_data: Dict[str, Any], store: Optional[MeteringStore] = None
) -> Dict[str, Any]:
    """Idempotently create/lookup the metering grant for a signed license.

    Uses purchase_order = license_id as the stable key, so issuing the same
    license twice returns the same grant (never re-mints tokens).
    """
    store = store or _default_store
    license_id = license_data.get("license_id")
    if not license_id:
        raise EntitlementError("license missing license_id", license_data)

    existing = store.get_grant_by_purchase_order(license_id)
    if existing:
        return existing

    customer = license_data.get("customer") or license_id
    org_type = "gov" if license_data.get("tier") == "enterprise_gov" else "credit_union"
    customer_id = store.register_customer(customer, org_type=org_type, customer_id=f"cus_{license_id[:32]}")
    return store.issue_grant(
        customer_id=customer_id["id"],
        token_pool=tokens_for_license(license_data),
        expires_at=_license_expiry(license_data),
        kind="licensed",
        tier=license_data.get("tier", "dev"),
        price_per_token_mills=0,
        purchase_order=license_id,
    )


def renew_grant_for_license(
    license_data: Dict[str, Any], store: Optional[MeteringStore] = None
) -> Dict[str, Any]:
    """Extend the grant bound to a renewed (re-signed) license."""
    store = store or _default_store
    return store.renew_grant(license_data["license_id"], _license_expiry(license_data))


def grant_for_key(api_key: str, store: Optional[MeteringStore] = None) -> Optional[Dict[str, Any]]:
    """Resolve an API key to its grant, or None when unknown/revoked."""
    store = store or _default_store
    key = store.verify_api_key(api_key)
    if not key:
        return None
    grant = store.get_grant(key["grant_id"])
    if not grant:
        return None
    grant["_key_permissions"] = key["permissions"]
    return grant


def _feature_enabled(feature: str, grant: Dict[str, Any], tier: str) -> bool:
    """Feature flags survive on the grant: derive from tier + allowlist."""
    if tier == "enterprise_gov":
        return feature in ("offense", "defense", "connector")
    if tier == "enterprise":
        return feature in ("offense", "defense")
    if tier == "dev":
        return feature in ("defense",)
    return False


def metered_authorize(
    api_key: str,
    endpoint: str,
    feature: Optional[str] = None,
    cost: int = 1,
    tx_hash: Optional[str] = None,
    store: Optional[MeteringStore] = None,
) -> Dict[str, Any]:
    """Verify API key + feature flag + reserve `cost` tokens atomically.

    Raises the same typed EntitlementError subclasses as authorize_reservation
    (NoEntitlementError / OutOfTokensError / InsufficientTokensError) so callers
    can map them to 401/402/403. Returns an authorize_reservation dict.
    """
    store = store or _default_store
    key = store.verify_api_key(api_key)
    if not key:
        raise NoEntitlementError("Unknown or revoked API key", {"status": "no_key"})
    if feature is not None:
        grant = store.get_grant(key["grant_id"])
        if not grant:
            raise NoEntitlementError("No active grant for this API key", grant or {})
        if not _feature_enabled(feature, grant, grant["tier"]):
            raise EntitlementError(f"Feature {feature} not licensed for tier {grant['tier']}", grant)
    return store.authorize_reservation(api_key, endpoint=endpoint, tokens=cost, tx_hash=tx_hash)


def get_connector_qps(store: Optional[MeteringStore] = None) -> int:
    """Informational QPS for the connector middleware (enforcement is per-token)."""
    return int(getattr(settings, "connector_qps", None) or 10)


def grant_summary(grant: Dict[str, Any]) -> Dict[str, Any]:
    """Map a metering grant to the legacy license-verify info shape."""
    return {
        "license_id": grant.get("purchase_order") or grant["id"],
        "tier": grant["tier"],
        "customer_id": grant["customer_id"],
        "expiry": grant["expires_at"],
        "status": grant["status"],
        "token_pool": grant["token_pool"],
        "tokens_consumed": grant["tokens_consumed"],
        "tokens_remaining": max(0, grant["token_pool"] - grant["tokens_consumed"] - grant["tokens_reserved"]),
        "kind": grant["kind"],
    }
