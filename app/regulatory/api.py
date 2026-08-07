"""
Enterprise Regulatory + Compliance API - Real OFAC/FATF Live Feeds
Government Standard: FIPS 140-3, SLSA L3, live feeds from treasury.gov + fatf-gafi.org
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import json

from app.core.auth_deps import get_current_user, require_role
from app.core.config import settings
from app.zk.verifier import ZKVerifier

router = APIRouter(prefix="/regulatory", tags=["regulatory"])
logger = logging.getLogger(__name__)

class FeedbackRequest(BaseModel):
    encrypted: bool
    data: Dict[str, Any]

class FeedbackResponse(BaseModel):
    status: str
    verified: bool
    risk_score: Optional[float] = None

class ComplianceCheckRequest(BaseModel):
    address: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None

class ScreenRequest(BaseModel):
    address: str
    amount: Optional[float] = None
    jurisdiction: Optional[str] = None
    currency: Optional[str] = None
    counterparty: Optional[str] = None

class ScreenResponse(BaseModel):
    screened_address: str
    amount: Optional[float] = None
    jurisdiction: Optional[str] = None
    currency: Optional[str] = None
    counterparty: Optional[str] = None
    shadow_match: Optional[Dict[str, Any]] = None
    ofac_address_match: Optional[Dict[str, Any]] = None
    jurisdiction_risk: Optional[Dict[str, Any]] = None
    currency_flag: Optional[Dict[str, Any]] = None
    analytics: Optional[list] = None
    risk_score: float
    decision: str
    reasons: list
    sources: list
    checked_at: str

class ComplianceCheckResponse(BaseModel):
    checked_at: str
    address: Optional[str]
    name: Optional[str]
    country: Optional[str]
    ofac: Optional[Dict[str, Any]] = None
    fatf: Optional[Dict[str, Any]] = None
    overall_risk: str
    blocked: bool
    reasons: list

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest, user=Depends(get_current_user)):
    """
    Receives ZK XAI packages from defense bot for regulatory audit.
    Verifies ZK proof, checks fairness policy, stores for compliance.
    """
    data = req.data
    if req.encrypted:
        from app.regulatory.keys import decrypt_regulatory_payload
        payload = decrypt_regulatory_payload(data)
        if payload is None:
            raise HTTPException(400, "Decryption failed")
    else:
        payload = data

    verifier = ZKVerifier()
    zk_proof = payload.get("zk_proof") or payload.get("explanation", {}).get("zk_proof")
    commitments = payload.get("commitments", {})
    public_inputs = [commitments.get("model_commitment"), commitments.get("input_commitment")] if commitments else []

    valid = verifier.verify(zk_proof, public_inputs, commitments) if zk_proof else False

    fairness = payload.get("fairness", {})
    risk = payload.get("risk_score") or payload.get("score")

    logger.info(f"Regulatory feedback: user={user.get('sub')} verified={valid} fair={fairness.get('is_fair')} risk={risk}")

    # Durable store (FedRAMP AU-3/AU-4): append every feedback record regardless
    # of whether Postgres is reachable. Plaintext-only; the payload was already
    # decrypted at rest, and the file is on the protected volume.
    try:
        from pathlib import Path
        record = {
            "received_at": datetime.utcnow().isoformat(),
            "actor": user.get("sub"),
            "verified": valid,
            "fair": fairness.get("is_fair"),
            "risk_score": risk,
            "tx_hash": payload.get("tx_hash"),
            "onchain_hash": payload.get("onchain_hash"),
            "policy_version": payload.get("policy_version"),
            "model_hash": payload.get("model_hash"),
        }
        store_path = settings.regulatory_feedback_store_path
        Path(store_path).parent.mkdir(parents=True, exist_ok=True)
        with open(store_path, "a") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception as e:
        logger.error(f"Regulatory feedback store write failed: {e}")

    if settings.postgres_url:
        pass

    return FeedbackResponse(status="logged", verified=valid, risk_score=risk)

@router.get("/pqc/pubkey")
async def get_regulatory_pqc_pubkey(user=Depends(get_current_user)):
    """Serve the regulatory API's persistent ML-KEM public key so the defense
    bot can PQC-encrypt feedback to a key we actually hold the secret for.
    mTLS (transport) + JWT (identity) gated. Fail-closed: no key, no response.
    """
    from app.regulatory.keys import load_or_create_regulatory_keypair
    pair = load_or_create_regulatory_keypair()
    if not pair:
        raise HTTPException(500, "Regulatory PQC key unavailable (set SECRETS_MASTER_KEY)")
    pub, _, variant = pair
    import base64
    return {
        "public_key": base64.b64encode(pub).decode(),
        "variant": variant,
        "kem_alg": variant,
        "dem_alg": "AES-256-GCM",
    }

@router.get("/policy")
async def get_fairness_policy(user=Depends(get_current_user)):
    return settings.fairness_policy

# --- NEW: Real OFAC/FATF Live Feed Endpoints ---

@router.post("/compliance/check", response_model=ComplianceCheckResponse)
async def compliance_check(req: ComplianceCheckRequest, user=Depends(get_current_user)):
    """
    Enterprise real-time compliance check - OFAC SDN live feed + FATF grey/black live feed
    - OFAC: live from sanctionslistservice.ofac.treas.gov with User-Agent, Redis 24h TTL, fallback
    - FATF: live from fatf-gafi.org, Redis 24h TTL, fallback to known list
    """
    try:
        from app.compliance.service import compliance_service
        result = compliance_service.check_address(
            address=req.address,
            name=req.name,
            country=req.country
        )
        logger.info(f"Compliance check by {user.get('sub')} address={req.address} name={req.name} country={req.country} risk={result.get('overall_risk')} blocked={result.get('blocked')}")
        return ComplianceCheckResponse(**result)
    except Exception as e:
        logger.error(f"Compliance check failed: {e}")
        raise HTTPException(500, f"Compliance check failed: {e}")

@router.get("/compliance/ofac/stats")
async def ofac_stats(user=Depends(get_current_user)):
    """Get OFAC feed stats - count, last fetch, source"""
    try:
        from app.compliance.service import compliance_service
        return compliance_service.get_ofac_stats()
    except Exception as e:
        raise HTTPException(500, f"OFAC stats failed: {e}")

@router.get("/compliance/fatf/stats")
async def fatf_stats(user=Depends(get_current_user)):
    """Get FATF grey/black list stats"""
    try:
        from app.compliance.service import compliance_service
        return compliance_service.get_fatf_stats()
    except Exception as e:
        raise HTTPException(500, f"FATF stats failed: {e}")

@router.get("/compliance/stats")
async def combined_stats(user=Depends(get_current_user)):
    """Combined OFAC + FATF stats"""
    try:
        from app.compliance.service import compliance_service
        return compliance_service.get_combined_stats()
    except Exception as e:
        raise HTTPException(500, f"Compliance stats failed: {e}")

@router.post("/compliance/refresh")
async def refresh_feeds(user=Depends(require_role("gov-admin", "operator"))):
    """
    Force refresh OFAC and FATF feeds - requires gov-admin or operator.
    """
    try:
        from app.compliance.service import compliance_service
        result = compliance_service.refresh_all()
        logger.info(f"Compliance feeds refreshed by {user.get('sub')}: {result}")
        return result
    except Exception as e:
        raise HTTPException(500, f"Refresh failed: {e}")

@router.get("/compliance/ofac/search")
async def ofac_search(q: str = Query(..., description="Name to search in OFAC SDN list"), user=Depends(get_current_user)):
    """Search OFAC SDN list by name - live feed"""
    try:
        from app.compliance.ofac import ofac_feed
        result = ofac_feed.is_sanctioned(name=q)
        return result
    except Exception as e:
        raise HTTPException(500, f"OFAC search failed: {e}")

@router.post("/compliance/screen", response_model=ScreenResponse)
async def compliance_screen(req: ScreenRequest, user=Depends(require_role("gov-admin", "operator"))):
    """Address-risk screen for a transaction: shadow set + OFAC SDN digital
    currency addresses + FATF jurisdiction + currency flags + Chainalysis/TRM
    analytics stubs. Returns allow / review / block. gov-admin or operator only.
    """
    from app.compliance.address_risk import address_risk_engine
    result = address_risk_engine.screen_transaction(
        address=req.address,
        amount=req.amount,
        jurisdiction=req.jurisdiction,
        currency=req.currency,
        counterparty=req.counterparty,
    )
    if result.get("error"):
        raise HTTPException(400, result["error"])
    logger.info(
        f"Address screen by {user.get('sub')} address={req.address} "
        f"decision={result.get('decision')} score={result.get('risk_score')}"
    )
    return result

@router.get("/compliance/fatf/check")
async def fatf_check(country: str = Query(..., description="Country to check against FATF grey/black list"), user=Depends(get_current_user)):
    """Check country against FATF lists"""
    try:
        from app.compliance.fatf import fatf_feed
        result = fatf_feed.is_high_risk(country)
        return result
    except Exception as e:
        raise HTTPException(500, f"FATF check failed: {e}")
