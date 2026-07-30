"""
API Key Management - Enterprise
GAP8: Complete API key management

- Create, list, revoke API keys
- Tied to license_id and customer
- Permissions: read, protect, mev, admin
- Prefix: protean_live_ / protean_test_ + random + checksum
- Stored in Postgres in prod, in-memory for demo
- Usage tracking via Redis + Postgres
"""

import secrets
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory for demo, Postgres in prod via k8s
api_keys_db: Dict[str, Dict] = {}

def generate_api_key(customer: str, license_id: str, name: str, permissions: List[str] = None, tier: str = "dev") -> Dict[str, str]:
    permissions = permissions or ["read", "protect"]
    
    # Format: protean_live_<random>_<checksum> for live, protean_test_ for test
    env = "live" if tier in ["enterprise", "enterprise_gov"] else "test"
    prefix = f"protean_{env}_"
    random_part = secrets.token_urlsafe(32)
    checksum = hashlib.sha256(f"{random_part}{customer}{license_id}".encode()).hexdigest()[:8]
    api_key = f"{prefix}{random_part}_{checksum}"

    record = {
        "api_key": api_key,
        "customer": customer,
        "license_id": license_id,
        "name": name,
        "permissions": permissions,
        "tier": tier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
        "usage_count": 0,
        "prefix": api_key[:20] + "...",
        "status": "active"
    }
    
    api_keys_db[api_key] = record
    
    logger.info(f"API key created: {name} for customer {customer} license {license_id} tier {tier}")
    
    return record

def list_api_keys(license_id: Optional[str] = None, customer: Optional[str] = None) -> List[Dict]:
    keys = list(api_keys_db.values())
    if license_id:
        keys = [k for k in keys if k["license_id"] == license_id]
    if customer:
        keys = [k for k in keys if k["customer"] == customer]
    
    # Sanitize: don't return full key in list, only prefix
    sanitized = []
    for k in keys:
        sanitized.append({
            "name": k["name"],
            "customer": k["customer"],
            "license_id": k["license_id"],
            "permissions": k["permissions"],
            "tier": k["tier"],
            "created_at": k["created_at"],
            "last_used": k["last_used"],
            "usage_count": k["usage_count"],
            "prefix": k["prefix"],
            "status": k["status"]
        })
    return sanitized

def get_api_key_info(api_key: str) -> Optional[Dict]:
    return api_keys_db.get(api_key)

def revoke_api_key(api_key_prefix: str) -> bool:
    found = None
    for full_key in list(api_keys_db.keys()):
        if full_key.startswith(api_key_prefix) or full_key[:20] in api_key_prefix or api_key_prefix in full_key:
            found = full_key
            break
    
    if found:
        api_keys_db[found]["status"] = "revoked"
        # Actually delete for gov standard - revoked keys should not be usable
        del api_keys_db[found]
        logger.info(f"API key revoked: {api_key_prefix}")
        return True
    return False

def validate_api_key(api_key: str, required_permission: Optional[str] = None) -> Dict:
    """
    Validate API key and check permission
    Returns key info if valid, raises PermissionError if invalid
    """
    record = api_keys_db.get(api_key)
    if not record:
        raise PermissionError(f"API key not found or revoked: {api_key[:20]}...")
    
    if record["status"] != "active":
        raise PermissionError(f"API key not active: {record['status']}")

    if required_permission and required_permission not in record["permissions"] and "admin" not in record["permissions"]:
        raise PermissionError(f"API key missing permission {required_permission}, has {record['permissions']}")

    # Update last used and usage count
    record["last_used"] = datetime.now(timezone.utc).isoformat()
    record["usage_count"] += 1

    return record

def get_api_key_tier(api_key: str) -> str:
    record = api_keys_db.get(api_key)
    return record["tier"] if record else "invalid"
