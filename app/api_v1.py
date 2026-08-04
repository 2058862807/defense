"""
Universal metered REST API (C2 / C1) - the integration surface every credit
union, bank, and exchange calls.

  * POST /v1/transactions/analyze          - full tx analysis (score + SHAP + ZK
                                             + OFAC/FATF screening), 1 token
  * POST /v1/compliance/check              - party screening (OFAC/FATF), 1 token
  * POST /v1/integrations/iso20022/analyze - ISO 20022 XML payment/statement
  * POST /v1/integrations/fix/analyze      - FIX 4.4 order message
  * POST /v1/integrations/core-banking/{provider}/analyze
  * POST /v1/webhooks/register             - signed webhook delivery subscription
  * GET  /v1/entitlement                   - token balance / expiry / offer

Token lifecycle per request: authorize (reserve) -> analyze -> settle; any
failure releases the reservation so the pilot only pays for completed analyses.
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.ledger import ledger
from app.core.logging import audit_log
from app.metering.deps import MeteredKey, require_metered_key
from app.metering.store import metering_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["v1-api"])


class TxAnalyzeRequest(BaseModel):
    type: str = Field("swap", pattern=r"^(swap|arbitrage|liquidation|sandwich|payment|transfer|order)$")
    value_eth: float = Field(..., ge=0, le=1_000_000_000)
    gas_price_gwei: float = Field(default=0, ge=0, le=10000)
    slippage_bps: float = Field(default=0, ge=0, le=10000)
    pool_liquidity_eth: float = Field(default=0, ge=0)
    is_protected_user: int = Field(default=1, ge=0, le=1)
    router: str = Field(default="", pattern=r"^$|^0x[a-fA-F0-9]{40}$")
    mode: str = Field("auto", pattern=r"^(offense|defense|auto)$")
    tx_hash: str = Field(default="")
    parties: List[Dict[str, Any]] = Field(default_factory=list)


class ComplianceCheckRequest(BaseModel):
    address: Optional[str] = Field(default=None, pattern=r"^$|^0x[a-fA-F0-9]{40}$")
    name: Optional[str] = None
    country: Optional[str] = None


class WebhookRegisterRequest(BaseModel):
    url: str = Field(..., min_length=8)
    events: List[str] = ["tx.analyzed", "compliance.checked"]


class ISO20022AnalyzeRequest(BaseModel):
    message: str = Field(..., description="Raw ISO 20022 XML")


class FIXAnalyzeRequest(BaseModel):
    message: str = Field(..., description="FIX 4.4 tag=value message (SOH or | delimited)")


# --------------------------------------------------------------------- #
# Shared analysis engine
# --------------------------------------------------------------------- #
def _analyze_blocking(tx_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run score + SHAP + real Groth16 ZK proof (blocking; run in a thread)."""
    from app.main import xai_coupler
    return xai_coupler.generate_zk_proof(tx_data)


def _compliance_blocking(parties: List[Dict[str, Any]]) -> Dict[str, Any]:
    from app.compliance.service import compliance_service
    results = []
    blocked = False
    reasons: List[str] = []
    for p in parties:
        if not (p.get("name") or p.get("address")):
            continue
        res = compliance_service.check_address(
            address=p.get("address"),
            name=p.get("name"),
            country=p.get("country"),
        )
        results.append(res)
        if res.get("blocked"):
            blocked = True
        reasons.extend(res.get("reasons", []))
    return {"parties": results, "blocked": blocked, "reasons": reasons}


async def _run_metered_analysis(
    key: MeteredKey,
    tx_data: Dict[str, Any],
    parties: List[Dict[str, Any]],
    event_source: str = "api",
) -> Dict[str, Any]:
    """Reserve -> analyze -> settle (or release on failure)."""
    res = key.reservation
    try:
        zk_package = await asyncio.to_thread(_analyze_blocking, tx_data)
        compliance = await asyncio.to_thread(_compliance_blocking, parties)

        score = float(zk_package["score"])
        if score > 0.7:
            decision = "block"
        elif score > 0.45:
            decision = "step"
        else:
            decision = "pass"
        if compliance.get("blocked"):
            decision = "block"

        tx_hash = tx_data.get("tx_hash") or zk_package.get("commitments", {}).get("input_commitment", "")
        entry = ledger.append(
            event_type="METERED_TX_ANALYZED",
            payload={
                "grant_id": res["grant_id"],
                "score": score,
                "decision": decision,
                "source": event_source,
                "zk_status": zk_package.get("zk_status"),
            },
            tx_hash=tx_hash or None,
            status=decision,
        )

        settled = metering_store.settle_reservation(
            res["reservation_id"],
            event_type="tx_analysis",
            decision=decision,
            score=score,
            ledger_entry_hash=entry["entry_hash"],
        )

        verdict = {
            "score": score,
            "risk_score": round(score * 100, 1),
            "is_fair": zk_package["fairness"]["is_fair"],
            "decision": decision,
            "zk_status": zk_package.get("zk_status"),
            "zk_proof_present": bool(zk_package.get("zk_proof")),
            "commitments": zk_package["commitments"],
            "explanation": zk_package["explanation"],
            "compliance": compliance,
            "onchain_hash": zk_package.get("onchain_hash", ""),
            "model_hash": zk_package["commitments"]["model_commitment"],
            "policy_version": settings.fairness_policy_version,
            "tokens_remaining": settled.get("tokens_remaining"),
            "grant_id": res["grant_id"],
        }

        audit_log(
            "V1_TX_ANALYZED", key.customer_id, "analyze", tx_hash or "unknown",
            decision, {"grant_id": res["grant_id"], "score": score, "source": event_source},
        )

        from app.integrations.events import publisher
        await publisher.publish_decision(
            {
                "event_type": "tx.analyzed",
                "grant_id": res["grant_id"],
                "customer_id": key.customer_id,
                "tx_hash": tx_hash,
                "score": score,
                "risk_score": round(score * 100, 1),
                "decision": decision,
                "source": event_source,
                "zk_status": zk_package.get("zk_status"),
                "timestamp": datetime.utcnow().isoformat(),
            },
            customer_id=key.customer_id,
        )
        return verdict
    except Exception as e:
        metering_store.release_reservation(res["reservation_id"])
        logger.error(f"Metered analysis failed (tokens released): {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


# --------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------- #
@router.post("/transactions/analyze")
async def analyze_transaction(
    req: TxAnalyzeRequest,
    key: MeteredKey = Depends(require_metered_key(1)),
):
    tx_data = req.model_dump(exclude={"parties"})
    verdict = await _run_metered_analysis(key, tx_data, req.parties, event_source="api")
    return verdict


@router.post("/compliance/check")
async def compliance_check(
    req: ComplianceCheckRequest,
    key: MeteredKey = Depends(require_metered_key(1)),
):
    res = key.reservation
    try:
        parties = [{"name": req.name, "address": req.address, "country": req.country}]
        compliance = await asyncio.to_thread(_compliance_blocking, parties)
        entry = ledger.append(
            event_type="METERED_COMPLIANCE_CHECK",
            payload={"grant_id": res["grant_id"], "address": req.address, "blocked": compliance.get("blocked")},
            tx_hash=req.address or None, status="blocked" if compliance.get("blocked") else "passed",
        )
        settled = metering_store.settle_reservation(
            res["reservation_id"], event_type="compliance_check",
            decision="block" if compliance.get("blocked") else "pass", score=0.0,
            ledger_entry_hash=entry["entry_hash"],
        )
        return {
            "compliance": compliance,
            "tokens_remaining": settled.get("tokens_remaining"),
            "grant_id": res["grant_id"],
        }
    except Exception as e:
        metering_store.release_reservation(res["reservation_id"])
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {e}")


@router.post("/entitlement")
async def entitlement(key: MeteredKey = Depends(require_metered_key(0))):
    """Current token balance / expiry for the API key's grant."""
    balance = metering_store.grant_balance(key.grant_id)
    from app.metering.service import license_offer
    grant = metering_store.get_grant(key.grant_id)
    offer = None
    if balance.get("tokens_remaining", 0) == 0 or balance.get("expired"):
        offer = license_offer(grant, reason="pilot_exhausted" if balance.get("tokens_remaining") == 0 else "grant_expired")
    return {"grant_id": key.grant_id, "customer_id": key.customer_id, "tier": key.tier,
            "balance": balance, "offer": offer}


@router.post("/integrations/iso20022/analyze")
async def iso20022_analyze(
    req: ISO20022AnalyzeRequest,
    key: MeteredKey = Depends(require_metered_key(1)),
):
    from app.integrations.iso20022 import ISO20022Adapter
    adapter = ISO20022Adapter()
    try:
        parsed = adapter.parse(req.message)
    except Exception as e:
        metering_store.release_reservation(key.reservation["reservation_id"])
        raise HTTPException(400, f"Invalid ISO 20022 message: {e}")

    analysis = adapter.to_analysis_request(parsed)
    parties = [{"name": p.get("name"), "address": p.get("id"), "country": p.get("country")} for p in parsed.get("parties", [])]
    tx_data = {
        "type": "payment",
        "value_eth": analysis.get("amount", 0),
        "gas_price_gwei": 0,
        "slippage_bps": 0,
        "pool_liquidity_eth": 0,
        "is_protected_user": 1,
        "mode": "defense",
        "tx_hash": analysis.get("uetr") or analysis.get("message_id") or "",
    }
    verdict = await _run_metered_analysis(key, tx_data, parties, event_source="iso20022")
    verdict["message_id"] = analysis.get("message_id")
    return adapter.verdict_to_message(verdict)


@router.post("/integrations/fix/analyze")
async def fix_analyze(
    req: FIXAnalyzeRequest,
    key: MeteredKey = Depends(require_metered_key(1)),
):
    from app.integrations.fix import parse_fix, to_analysis_request, verdict_to_fix, FIXParseError
    try:
        parsed = parse_fix(req.message)
    except (FIXParseError, ValueError) as e:
        metering_store.release_reservation(key.reservation["reservation_id"])
        raise HTTPException(400, f"Invalid FIX message: {e}")

    analysis = to_analysis_request(parsed)
    tx_data = {
        "type": "order",
        "value_eth": analysis.get("amount", 0),
        "gas_price_gwei": 0,
        "slippage_bps": analysis.get("slippage_bps", 5),
        "pool_liquidity_eth": 0,
        "is_protected_user": analysis.get("is_protected_user", 0),
        "mode": "defense",
        "tx_hash": analysis.get("cl_ord_id") or "",
    }
    verdict = await _run_metered_analysis(key, tx_data, [], event_source="fix")
    return {"verdict": verdict, "fix_response": verdict_to_fix(verdict, parsed)}


@router.post("/integrations/core-banking/{provider}/analyze")
async def core_banking_analyze(
    provider: str,
    payload: Dict[str, Any],
    key: MeteredKey = Depends(require_metered_key(1)),
):
    from app.integrations.core_banking import get_adapter
    try:
        adapter = get_adapter(provider)
    except ValueError as e:
        metering_store.release_reservation(key.reservation["reservation_id"])
        raise HTTPException(400, str(e))

    analysis = adapter.to_analysis_request(payload)
    parties = [{"name": analysis.get("debtor"), "address": None, "country": None}]
    tx_data = {
        "type": "payment" if analysis.get("type") == "transfer" else "transfer",
        "value_eth": analysis.get("amount", 0),
        "gas_price_gwei": 0,
        "slippage_bps": 0,
        "pool_liquidity_eth": 0,
        "is_protected_user": analysis.get("is_protected_user", 1),
        "mode": "defense",
        "tx_hash": analysis.get("external_id") or "",
    }
    verdict = await _run_metered_analysis(key, tx_data, parties, event_source=f"core_banking:{provider}")
    return {"verdict": verdict, "vendor_response": adapter.to_vendor_response(verdict)}


@router.post("/webhooks/register")
async def register_webhook(
    req: WebhookRegisterRequest,
    key: MeteredKey = Depends(require_metered_key(0)),
):
    from app.integrations.webhooks import register_webhook as _register
    hook = _register(key.customer_id, req.url, req.events)
    return {"webhook": {k: v for k, v in hook.items() if k != "secret"}, "signing_secret": hook["secret"]}


@router.get("/webhooks")
async def list_webhooks(key: MeteredKey = Depends(require_metered_key(0))):
    from app.integrations.webhooks import list_webhooks as _list
    return {"webhooks": _list(key.customer_id)}
