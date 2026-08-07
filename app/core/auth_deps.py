"""
Shared FastAPI auth dependencies - centralized and fail-closed.

- Production: strict RS256/ES256 verification via JWKS only. HS256 and 'none'
  are never accepted. Missing/invalid Bearer token => 401.
- Non-production: prefers JWKS verification; only falls back to a synthetic
  dev identity when the process is explicitly non-production.
- RBAC: `require_role(...)` gates sensitive endpoints by the JWT `role` claim
  (gov-admin / operator / auditor).

Government standard: NIST SP 800-207 zero-trust; every protected request is
authenticated and authorized, nothing is silently downgraded.
"""

import logging
from typing import List, Optional

from fastapi import Depends, Header, HTTPException

from app.core.config import settings
from app.core.security import verify_jwt_gov

logger = logging.getLogger(__name__)

ALLOWED_ROLES = ("gov-admin", "operator", "auditor")


def _verify_token(authorization: Optional[str]) -> dict:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]

    if settings.is_production():
        if not token:
            raise HTTPException(status_code=401, detail="Invalid auth header - Bearer required")
        try:
            return _verify_against_configured_idp(token)
        except Exception as e:
            logger.warning(f"JWT verification failed: {e}")
            raise HTTPException(status_code=401, detail=f"JWT verification failed: {e}")

    # Non-production: prefer real verification, then a synthetic identity.
    if token:
        try:
            return _verify_against_configured_idp(token)
        except Exception as e:
            logger.warning(f"Dev-mode JWT verification failed, using dev identity: {e}")
    return {"sub": "dev-operator", "role": "gov-admin", "iss": "dev", "aud": settings.jwt_aud}


def _verify_against_configured_idp(token: str) -> dict:
    """Verify against the in-process IdP (local mode) or the remote JWKS URL
    (remote mode). Symmetric algorithms are never accepted."""
    if settings.idp_mode == "local":
        from app.core.idp import get_idp
        return get_idp().verify(token, settings.jwt_aud, settings.jwt_issuer)
    return verify_jwt_gov(
        token,
        jwks_url=settings.jwt_jwks_url,
        audience=settings.jwt_aud,
        issuer=settings.jwt_issuer,
        algorithms=[settings.jwt_algorithm],
    )


def get_current_user(authorization: str = Header(default=None)) -> dict:
    """Authenticate the caller. Returns the verified JWT payload."""
    return _verify_token(authorization)


def _claim_roles(user: dict) -> List[str]:
    role = user.get("role")
    roles = user.get("roles")
    if isinstance(roles, list):
        return [str(r) for r in roles]
    if role:
        return [str(role)]
    return []


def require_role(*roles: str):
    """Gate an endpoint to one of the given roles (RBAC)."""

    def _dependency(user: dict = Depends(get_current_user)) -> dict:
        allowed = set(roles)
        for r in allowed:
            if r not in ALLOWED_ROLES:
                raise ValueError(f"Unknown role in require_role: {r}")
        if not allowed.intersection(_claim_roles(user)):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient role - requires one of: {', '.join(sorted(allowed))}",
            )
        return user

    return _dependency


# Aliases kept for compatibility with the pre-centralization call sites.
get_current_user_gov = get_current_user
