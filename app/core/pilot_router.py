"""
Pilot credential admin API (gov-admin only).

A pilot / operator enters real third-party credentials (Chainalysis, TRM,
Qrypt, Azure, AWS, CloudHSM, Securosys, Flashbots, EVM signer) at runtime.
Credentials persist in the encrypted secrets store (data/secrets.enc) and are
picked up live by providers - no restart required.

Security:
  * Every route requires gov-admin RBAC (fail-closed).
  * Values are never echoed back; status reports configured/source only.
  * Every write is audit-logged (never the secret itself).
  * Runtime integrations that cache credentials at construction are refreshed
    on write/delete so newly entered tokens apply immediately.

Endpoints:
  * GET    /pilot/credentials          - status snapshot (no values)
  * POST   /pilot/credentials/{field}  - set a credential + refresh integrations
  * DELETE /pilot/credentials/{field}  - remove a stored credential + refresh
  * POST   /pilot/credentials/refresh  - force re-init of QRNG/HSM integrations
  * GET    /pilot/status               - per-integration readiness surface
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth_deps import require_role
from app.core.logging import audit_log
from app.core.pilot_secrets import PILOT_CREDENTIALS, pilot_secrets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pilot", tags=["pilot"])

_admin = Depends(require_role("gov-admin"))


def _audit(action: str, field: str, user: dict, metadata: dict) -> None:
    try:
        audit_log(
            event_type="PILOT_CREDENTIAL",
            actor=user.get("sub", "unknown"),
            action=action,
            resource=f"pilot/credentials/{field}",
            result="SUCCESS",
            metadata=metadata,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")


@router.get("/credentials")
def list_credentials(_user: dict = _admin):
    """Status snapshot of every pilot credential field (never the values)."""
    return {"credentials": pilot_secrets.snapshot()}


@router.post("/credentials/refresh")
def refresh_credentials(_user: dict = _admin):
    """Force re-initialization of QRNG/HSM integrations from current creds."""
    pilot_secrets.refresh()
    return {"status": "refreshed", "integrations": ["qrng", "hsm"]}


@router.post("/credentials/{field}")
def set_credential(field: str, body: dict, _user: dict = _admin):
    """Store a credential value (env vars still win if set) + live refresh."""
    if field not in PILOT_CREDENTIALS:
        raise HTTPException(status_code=404, detail=f"Unknown pilot credential field: {field}")
    value = body.get("value")
    if not value or not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=422, detail="Body must include non-empty string 'value'")
    store_ok = pilot_secrets.store_health()["ok"]
    if not store_ok:
        raise HTTPException(
            status_code=503,
            detail="Encrypted secrets store not writable. Operator: bootstrap with "
                   "`venv/bin/python scripts/init_secrets.py --fresh --write-key-file`, or "
                   "inject SECRETS_MASTER_KEY via env/Vault.",
        )
    try:
        status = pilot_secrets.set(field, value.strip())
    except Exception as e:
        logger.error(f"Failed to store pilot credential {field}: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to store credential (secrets store unavailable): {e}")
    pilot_secrets.refresh()
    _audit("set", field, _user, {"configured": status.get("configured"), "source": status.get("source")})
    return {"updated": status}


@router.delete("/credentials/{field}")
def delete_credential(field: str, _user: dict = _admin):
    """Remove a stored credential; env-var credentials are untouched."""
    if field not in PILOT_CREDENTIALS:
        raise HTTPException(status_code=404, detail=f"Unknown pilot credential field: {field}")
    removed = pilot_secrets.delete(field)
    pilot_secrets.refresh()
    _audit("delete", field, _user, {"removed": removed})
    return {"field": field, "removed": removed}


@router.get("/status")
def status(_user: dict = _admin):
    """Per-integration readiness: what is configured and resolvable now."""
    creds = {s["field"]: s for s in pilot_secrets.snapshot()}

    integrations = {}
    try:
        from app.compliance.address_risk import address_risk_engine
        integrations["compliance"] = {
            "engine": "address-risk",
            "providers": address_risk_engine.status(),
        }
    except Exception as e:
        integrations["compliance"] = {"error": str(e)}

    try:
        from app.qrng.service import qrng_service
        integrations["qrng"] = {
            "providers": [p.get_provider_name() for p in qrng_service.providers],
            "cloud_available": bool(qrng_service.providers),
        }
    except Exception as e:
        integrations["qrng"] = {"error": str(e)}

    try:
        from app.hsm.service import hsm_service
        integrations["hsm"] = {
            "providers": [p.get_provider_name() for p in hsm_service.providers],
            "cloud_available": bool(hsm_service.providers),
        }
    except Exception as e:
        integrations["hsm"] = {"error": str(e)}

    try:
        from app.evm.flashbots import FlashbotsClientEnterprise
        client = FlashbotsClientEnterprise()
        auth_ready = client.auth_account is not None
        integrations["flashbots"] = {
            "auth_ready": auth_ready,
            "address": client.auth_account.address if auth_ready else None,
        }
    except Exception as e:
        integrations["flashbots"] = {"error": str(e)[:300]}

    try:
        from app.hsm.custody import get_account
        acct = get_account()
        integrations["signer"] = {
            "available": bool(acct),
            "address": str(acct.address) if acct and getattr(acct, "address", None) else None,
        }
    except Exception as e:
        integrations["signer"] = {"error": str(e)[:300]}

    return {
        "credentials": creds,
        "integrations": integrations,
        "store": pilot_secrets.store_health(),
        "checked_at": datetime.utcnow().isoformat(),
    }
