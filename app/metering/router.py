"""
Metering / token-licensing admin + payment API (C1).

Endpoints:
  * POST /metering/customers            - register a pilot customer (admin)
  * POST /metering/grants               - issue a fixed-pool pilot grant (admin)
  * POST /metering/grants/{id}/purchase - create a purchase token + offer
  * POST /metering/payments/webhook     - payment confirmation (signed)
  * POST /metering/api-keys             - create an API key bound to a grant (admin)
  * GET  /metering/grants               - list grants (admin)
  * GET  /metering/grants/{id}          - grant + balance (admin or key holder)
  * GET  /metering/usage                - usage records (admin or key holder)
  * POST /metering/audit/anchor         - anchor the current period commitment
  * GET  /metering/audit/commitment     - current period commitment (read-only)
"""
import hashlib
import hmac
import logging
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.auth_deps import require_role
from app.core.config import settings
from app.core.logging import audit_log

from app.metering import service
from app.metering.store import metering_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metering", tags=["metering"])

_TOPUP_TOKENS_ON_PURCHASE = 10_000_000


class CustomerCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    email: Optional[str] = None
    org_type: str = Field(default="credit_union", pattern=r"^(credit_union|bank|exchange|other)$")
    customer_id: Optional[str] = None


class GrantIssueRequest(BaseModel):
    customer_id: str
    token_pool: Optional[int] = Field(default=None, ge=1000)
    months: Optional[int] = Field(default=None, ge=1, le=24)
    tier: str = "pilot"
    kind: str = "pilot"
    price_per_token_mills: int = Field(default=0, ge=0)


class PurchaseRequest(BaseModel):
    purchase_order: Optional[str] = None


class APIKeyCreateRequest(BaseModel):
    customer_id: str
    grant_id: str
    name: str = Field(..., min_length=1, max_length=120)
    permissions: List[str] = ["analyze", "compliance"]


class PaymentWebhookRequest(BaseModel):
    purchase_token: str
    status: str = "paid"
    purchase_order: Optional[str] = None
    added_tokens: Optional[int] = None
    amount_cents: Optional[int] = None


@router.post("/customers")
async def register_customer(req: CustomerCreateRequest, user=Depends(require_role("gov-admin", "operator"))):
    customer = metering_store.register_customer(
        name=req.name, email=req.email, org_type=req.org_type, customer_id=req.customer_id
    )
    audit_log("METERING_CUSTOMER", user.get("sub"), "register_customer", customer["id"], "SUCCESS", {"org_type": req.org_type})
    return customer


@router.post("/grants")
async def issue_grant(req: GrantIssueRequest, user=Depends(require_role("gov-admin", "operator"))):
    if req.kind == "pilot":
        grant = metering_store.issue_pilot_grant(
            customer_id=req.customer_id,
            token_pool=req.token_pool,
            months=req.months,
            tier=req.tier,
        )
    else:
        grant = metering_store.issue_grant(
            customer_id=req.customer_id,
            token_pool=req.token_pool or settings.metering_pilot_token_pool,
            expires_at=service.expiry_iso(req.months or settings.metering_pilot_months),
            kind=req.kind,
            tier=req.tier,
            price_per_token_mills=req.price_per_token_mills,
        )
    audit_log("METERING_GRANT", user.get("sub"), "issue_grant", grant["id"], "SUCCESS",
              {"customer_id": req.customer_id, "token_pool": grant["token_pool"], "months": req.months})
    return {"grant": grant, "pilot_terms": {"months": req.months or settings.metering_pilot_months, "token_pool": grant["token_pool"]}}


@router.post("/grants/{grant_id}/purchase")
async def purchase_license(grant_id: str, req: PurchaseRequest, user=Depends(require_role("gov-admin", "operator"))):
    grant = metering_store.get_grant(grant_id)
    if not grant:
        raise HTTPException(404, "grant not found")
    token = service.create_purchase_token(grant_id)
    return {
        "purchase_token": token["purchase_token"],
        "grant_id": grant_id,
        "amount_cents": token["amount_cents"],
        "currency": token["currency"],
        "payment_webhook": settings.metering_payment_webhook_url or "/metering/payments/webhook",
        "purchase_order": req.purchase_order,
        "offer": service.license_offer(grant),
    }


@router.post("/payments/webhook")
async def payments_webhook(req: PaymentWebhookRequest, request: Request):
    """Payment confirmation from the billing provider (or an operator console).

    Verifies the HMAC signature over the raw body when
    METERING_PAYMENT_WEBHOOK_SECRET is configured (production), then converts a
    paid pilot grant to 'paid' and tops up the token pool.
    """
    if settings.metering_payment_webhook_secret:
        sig = request.headers.get("X-Protean-Signature", "")
        expected = "sha256=" + hmac.new(
            settings.metering_payment_webhook_secret.encode(),
            await request.body(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(401, "invalid webhook signature")

    if req.status != "paid":
        raise HTTPException(400, "status must be 'paid'")
    if not req.purchase_token.startswith("pt_"):
        raise HTTPException(400, "invalid purchase_token")

    # purchase_token encodes the grant_id it was created for (single-use in prod).
    # For this delivery the token prefix embeds a random id; we resolve via the
    # caller-provided grant_id stored at purchase time - here we require it be
    # recoverable by the operator passing the matching grant in purchase_order.
    grant_id = req.purchase_order or _grant_for_purchase_token(req.purchase_token)
    if not grant_id:
        raise HTTPException(400, "purchase_token does not resolve to a grant")

    added = req.added_tokens or _TOPUP_TOKENS_ON_PURCHASE
    try:
        grant = metering_store.mark_paid(grant_id, purchase_order=req.purchase_order or "webhook", added_tokens=added)
    except KeyError:
        raise HTTPException(404, "grant not found")

    audit_log("METERING_LICENSE_PAID", "payments", "webhook", grant_id, "SUCCESS",
              {"tokens_added": added, "amount_cents": req.amount_cents})
    return {"grant_id": grant_id, "status": grant["status"], "tokens_added": added,
            "tokens_remaining": metering_store.grant_balance(grant_id)["tokens_remaining"]}


def _grant_for_purchase_token(purchase_token: str) -> Optional[str]:
    return None  # in production the token maps 1:1 to a grant in the billing ledger


@router.post("/api-keys")
async def create_api_key(req: APIKeyCreateRequest, user=Depends(require_role("gov-admin", "operator"))):
    key = metering_store.create_api_key(req.customer_id, req.grant_id, req.name, req.permissions)
    audit_log("METERING_API_KEY", user.get("sub"), "create_api_key", key["key_prefix"], "SUCCESS",
              {"grant_id": req.grant_id})
    return key


@router.get("/grants")
async def list_grants(user=Depends(require_role("gov-admin", "operator", "auditor"))):
    grants = metering_store.list_grants()
    return {"grants": [metering_store.grant_balance(g["id"]) for g in grants], "count": len(grants)}


@router.get("/grants/{grant_id}")
async def get_grant(grant_id: str, user=Depends(require_role("gov-admin", "operator", "auditor"))):
    grant = metering_store.get_grant(grant_id)
    if not grant:
        raise HTTPException(404, "grant not found")
    return {"grant": grant, "balance": metering_store.grant_balance(grant_id)}


@router.get("/usage")
async def get_usage(grant_id: Optional[str] = None, customer_id: Optional[str] = None, since: Optional[str] = None, limit: int = 200,
                    user=Depends(require_role("gov-admin", "operator", "auditor"))):
    if grant_id:
        events = metering_store.usage_for_grant(grant_id, since=since, limit=limit)
    elif customer_id:
        events = []
        for g in metering_store.list_grants(customer_id=customer_id):
            events.extend(metering_store.usage_for_grant(g["id"], since=since, limit=limit))
        events = sorted(events, key=lambda e: e["created_at"], reverse=True)[:limit]
    else:
        events = metering_store.all_usage(since=since, limit=limit)
    total_tokens = sum(e["tokens"] for e in events)
    return {"events": events, "count": len(events), "tokens_consumed": total_tokens}


@router.get("/audit/commitment")
async def audit_commitment(user=Depends(require_role("gov-admin", "operator", "auditor"))):
    return service.period_commitment(metering_store, service.period_start())


@router.post("/audit/anchor")
async def audit_anchor(user=Depends(require_role("gov-admin", "operator"))):
    from app.core.ledger import ledger
    result = service.anchor_period(metering_store, ledger=ledger)
    audit_log("METERING_AUDIT_ANCHOR", user.get("sub"), "anchor", "period", "SUCCESS",
              {"commitment": result["commitment"]["commitment"]})
    return result
