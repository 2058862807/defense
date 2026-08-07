"""
FastAPI dependencies for metered endpoints.

`require_metered_key(cost)` authenticates an X-API-Key header, verifies the
backing grant (active + unexpired), and atomically reserves `cost` tokens so
the endpoint can settle on success or release on failure. Entitlement failures
map to typed HTTP errors:
  * 401 - missing key
  * 403 - unknown/revoked key or no active grant (NoEntitlementError)
  * 402 - pool exhausted / expired / insufficient (OutOfTokens / Insufficient)
          with a license offer in the response
"""
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException

from app.core.config import settings
from app.metering.store import (
    EntitlementError,
    InsufficientTokensError,
    MeteringStore,
    NoEntitlementError,
    OutOfTokensError,
    metering_store,
)
from app.metering.service import license_offer

logger = logging.getLogger(__name__)


@dataclass
class MeteredKey:
    api_key_hash: str
    key_prefix: str
    grant_id: str
    customer_id: str
    tier: str
    reservation: dict


def require_metered_key(
    cost: int = 1,
    store: Optional[MeteringStore] = None,
):
    """Dependency factory. Returns a dependency that reserves `cost` tokens."""

    def _dependency(x_api_key: Optional[str] = Header(default=None)) -> MeteredKey:
        if not x_api_key:
            raise HTTPException(status_code=401, detail="X-API-Key header required")
        st = store or metering_store
        try:
            reservation = st.authorize_reservation(x_api_key, endpoint="/v1", tokens=cost)
        except NoEntitlementError as e:
            raise HTTPException(status_code=e.http_status, detail=str(e))
        except (OutOfTokensError, InsufficientTokensError) as e:
            raise entitlement_error_response(e)
        except EntitlementError as e:
            raise HTTPException(status_code=e.http_status, detail=str(e))
        return MeteredKey(
            api_key_hash=reservation["key_hash"],
            key_prefix=reservation["key_prefix"],
            grant_id=reservation["grant_id"],
            customer_id=reservation["customer_id"],
            tier=reservation["tier"],
            reservation=reservation,
        )

    return _dependency


def optional_metered_key(
    cost: int = 1,
    store: Optional[MeteringStore] = None,
):
    """Like `require_metered_key` but returns None when no X-API-Key header is
    present, so existing JWT/mTLS-authenticated endpoints can meter only when a
    customer API key is supplied (backward compatible)."""

    def _dependency(x_api_key: Optional[str] = Header(default=None)) -> Optional[MeteredKey]:
        if not x_api_key:
            return None
        st = store or metering_store
        try:
            reservation = st.authorize_reservation(x_api_key, endpoint="/analyze", tokens=cost)
        except EntitlementError as e:
            raise HTTPException(
                status_code=e.http_status,
                detail=str(e),
                headers={"X-Protean-Entitlement": "pilot_exhausted"},
            )
        return MeteredKey(
            api_key_hash=reservation["key_hash"],
            key_prefix=reservation["key_prefix"],
            grant_id=reservation["grant_id"],
            customer_id=reservation["customer_id"],
            tier=reservation["tier"],
            reservation=reservation,
        )

    return _dependency


def entitlement_error_response(err: EntitlementError) -> HTTPException:
    """Build an HTTPException (with license offer) from an entitlement error."""
    offer = license_offer(getattr(err, "grant", None))
    return HTTPException(
        status_code=err.http_status,
        detail={"message": str(err), "offer": offer},
        headers={"X-Protean-Entitlement": "pilot_exhausted"},
    )
