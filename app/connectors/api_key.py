"""
API Key Management - Enterprise (metering-backed)
GAP8: Complete API key management

Retired the demo-era in-memory key store: keys now live in the durable
metering ledger (data/metering.db). This module keeps the legacy public API
(generate_api_key / list / validate / revoke / tier) for the connector and
licensing server while delegating all state to the metering store.
Plaintext keys are returned exactly once at creation (pk_live_...); the store
persists only a SHA-256 hash.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.metering.store import metering_store
from app.metering.migrate import grant_for_key

logger = logging.getLogger(__name__)


def _record(key: Dict, grant: Dict) -> Dict[str, str]:
    return {
        "api_key": key.get("api_key", key["key_prefix"]),
        "customer": grant["customer_id"],
        "license_id": grant.get("purchase_order") or grant["id"],
        "name": key["name"],
        "permissions": key["permissions"],
        "tier": grant["tier"],
        "created_at": key["created_at"],
        "last_used": None,
        "usage_count": 0,
        "prefix": key["key_prefix"],
        "status": "active" if not key.get("revoked_at") else "revoked",
    }


def generate_api_key(customer: str, license_id: str, name: str, permissions: List[str] = None, tier: str = "dev") -> Dict[str, str]:
    permissions = permissions or ["read", "protect"]
    grant = metering_store.get_grant_by_purchase_order(license_id)
    if not grant:
        raise PermissionError(f"No metering grant for license {license_id}")
    key = metering_store.create_api_key(grant["customer_id"], grant["id"], name, permissions=permissions)
    logger.info(f"API key created: {name} for customer {customer} license {license_id} tier {tier}")
    return _record(key, grant)


def list_api_keys(license_id: Optional[str] = None, customer: Optional[str] = None) -> List[Dict]:
    grant = metering_store.get_grant_by_purchase_order(license_id) if license_id else None
    keys = metering_store.list_keys(customer_id=customer, grant_id=grant["id"] if grant else None)

    sanitized = []
    for k in keys:
        sanitized.append({
            "name": k["name"],
            "customer": k["customer_id"],
            "permissions": k["permissions"],
            "tier": k.get("tier"),
            "created_at": k["created_at"],
            "last_used": None,
            "usage_count": 0,
            "prefix": k["key_prefix"],
            "status": "active" if not k.get("revoked_at") else "revoked",
        })
    return sanitized


def get_api_key_info(api_key: str) -> Optional[Dict]:
    grant = grant_for_key(api_key)
    if not grant:
        return None
    key = metering_store.verify_api_key(api_key)
    return _record(key, grant)


def revoke_api_key(api_key_prefix: str) -> bool:
    return metering_store.revoke_api_key(api_key_prefix)


def validate_api_key(api_key: str, required_permission: Optional[str] = None) -> Dict:
    """
    Validate API key and check permission (metering store backed).
    Returns key info if valid, raises PermissionError if invalid.
    """
    grant = grant_for_key(api_key)
    if not grant:
        raise PermissionError(f"API key not found or revoked: {api_key[:20]}...")
    if grant.get("status") != "active":
        raise PermissionError(f"API key not active: {grant['status']}")

    permissions = grant.get("_key_permissions") or []
    if required_permission and required_permission not in permissions and "admin" not in permissions:
        raise PermissionError(f"API key missing permission {required_permission}, has {permissions}")

    return _record(metering_store.verify_api_key(api_key), grant)


def get_api_key_tier(api_key: str) -> str:
    grant = grant_for_key(api_key)
    return grant["tier"] if grant else "invalid"
