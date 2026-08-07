"""Standalone ZK-XAI crown jewel showcase server.

One program, one purpose: score -> SHAP -> commitments -> real Groth16 proof
-> cryptographic verification, run fully offline against the committed
artifacts (model + SHAP background + circuit wasm/zkey/vkey). No auth, no
metering, no TLS, no network - just the crown jewel.

Run:
    venv/bin/python showcase/zkxai_server.py
Then open http://127.0.0.1:9090
"""
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.ml.scorer import ProteanScorerEnterprise
from app.ml.xai import ZKXAICouplerEnterprise
from app.zk.verifier import ZKVerifierEnterprise
from app.evm.fairness_registry import trans_verify_explanation
from app.core.config import settings

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

app = FastAPI(title="ZK-XAI Crown Jewel Showcase", docs_url=None, redoc_url=None)

scorer = ProteanScorerEnterprise()
coupler = ZKXAICouplerEnterprise(scorer)
verifier = ZKVerifierEnterprise()

SCENARIOS = [
    {
        "id": "sandwich_attack",
        "name": "Sandwich attack attempt",
        "tx_data": {
            "type": "sandwich",
            "value_eth": 8.0,
            "slippage_bps": 200,
            "gas_price_gwei": 95.0,
            "pool_liquidity": 2_000_000.0,
            "tx_count": 40,
            "is_router": 0,
            "is_protected": 0,
            "is_protected_user": 0,
        },
    },
    {
        "id": "protected_user",
        "name": "High-value protected user (fair)",
        "tx_data": {
            "type": "swap",
            "value_eth": 120.0,
            "slippage_bps": 30,
            "gas_price_gwei": 25.0,
            "pool_liquidity": 12_000_000.0,
            "tx_count": 150,
            "is_router": 1,
            "is_protected": 1,
            "is_protected_user": 1,
        },
    },
    {
        "id": "routine_swap",
        "name": "Routine market swap",
        "tx_data": {
            "type": "swap",
            "value_eth": 1.5,
            "slippage_bps": 45,
            "gas_price_gwei": 18.0,
            "pool_liquidity": 5_000_000.0,
            "tx_count": 220,
            "is_router": 0,
            "is_protected": 0,
            "is_protected_user": 0,
        },
    },
]

MODEL_COMMITMENT = None


class AnalyzeRequest(BaseModel):
    scenario_id: str = Field(default="routine_swap")
    value_eth: float = Field(default=None, ge=0)
    slippage_bps: int = Field(default=None, ge=0, le=10000)
    type: str = "swap"
    is_protected_user: int = 0
    is_protected: int = 0


def _risk_label(score: float) -> str:
    if score >= 0.7:
        return "HIGH"
    if score >= 0.4:
        return "MEDIUM"
    return "LOW"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML.read_text()


@app.get("/api/scenarios")
def scenarios():
    return {"scenarios": [{"id": s["id"], "name": s["name"]} for s in SCENARIOS]}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    scenario = next((s for s in SCENARIOS if s["id"] == req.scenario_id), SCENARIOS[0])
    tx_data = dict(scenario["tx_data"])
    if req.value_eth is not None:
        tx_data["value_eth"] = req.value_eth
    if req.slippage_bps is not None:
        tx_data["slippage_bps"] = req.slippage_bps
    tx_data["type"] = req.type
    tx_data["is_protected_user"] = req.is_protected_user
    tx_data["is_protected"] = req.is_protected

    t0 = time.time()
    try:
        pkg = coupler.generate_zk_proof(tx_data)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)[:500]})
    elapsed_ms = int((time.time() - t0) * 1000)

    proof = pkg.get("zk_proof")
    public_inputs = pkg.get("zk_public_inputs", [])
    commitments = pkg.get("commitments", {})
    t1 = time.time()
    offchain_ok = bool(proof) and verifier.verify_offchain(proof, public_inputs, commitments)
    onchain_ok = bool(proof) and verifier.verify_onchain(proof, public_inputs, commitments.get("input_commitment"))
    verified = bool(offchain_ok)
    verify_ms = int((time.time() - t1) * 1000)

    explanation = pkg.get("explanation", {})
    shap_values = explanation.get("shap_values", [])
    feature_names = explanation.get("feature_names", [])
    features = explanation.get("input", [])
    if features and isinstance(features[0], list):
        features = features[0]
    base_value = explanation.get("base_value", 0.5)
    score = pkg.get("score", 0.0)

    feature_rows = []
    for i, name in enumerate(feature_names):
        raw = features[i] if i < len(features) else 0
        shap = shap_values[i] if i < len(shap_values) else 0.0
        feature_rows.append({"name": name, "raw": raw, "shap": round(float(shap), 5)})
    feature_rows.sort(key=lambda r: abs(r["shap"]), reverse=True)

    fairness = pkg.get("fairness", {})
    provenance = pkg.get("provenance", {})
    tv = trans_verify_explanation(pkg)

    return {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "score": round(float(score), 4),
        "risk_level": _risk_label(float(score)),
        "base_value": round(float(base_value), 4),
        "features": feature_rows,
        "fairness": fairness,
        "commitments": commitments,
        "proof": {
            "status": pkg.get("zk_status"),
            "has_proof": bool(proof),
            "points": {
                "pi_a": proof.get("pi_a", []) if proof else [],
                "pi_b": proof.get("pi_b", []) if proof else [],
                "pi_c": proof.get("pi_c", []) if proof else [],
            },
        },
        "public_inputs": public_inputs,
        "verified": bool(verified),
        "onchain": {
            "verifier_address": settings.fairness_verifier_address,
            "chain_id": settings.evm_chain_id,
            "verified_onchain": bool(onchain_ok),
            "explorer": (
                f"https://polygonscan.com/address/{settings.fairness_verifier_address}"
                if settings.evm_chain_id == 137
                else f"https://etherscan.io/address/{settings.fairness_verifier_address}"
                if settings.evm_chain_id == 1
                else ""
            ),
        },
        "trans_verify": {
            "anchored_ok": tv.get("anchored_ok"),
            "matches": tv.get("matches", {}),
            "combined_commitment": tv.get("recomputed", {}).get("combined_commitment"),
            "note": tv.get("note"),
        },
        "provenance": {
            "model_hash": provenance.get("model_hash") or commitments.get("model_commitment"),
            "training_data_hash": provenance.get("training_data_hash"),
            "circuit_hash": provenance.get("circuit_hash"),
            "fips": provenance.get("fips"),
            "shap_version": explanation.get("shap_version"),
            "background_hash": explanation.get("background_hash"),
        },
        "elapsed_ms": elapsed_ms,
        "verify_ms": verify_ms,
        "model_info": {
            "model_hash": scorer.commitment.get("model_hash") if scorer.commitment else None,
            "model_version": scorer.commitment.get("version") if scorer.commitment else None,
        },
    }


if __name__ == "__main__":
    import uvicorn

    print("\n  ZK-XAI CROWN JEWEL SHOWCASE")
    print("  score -> SHAP -> commitments -> Groth16 proof -> verify\n")
    print("  http://127.0.0.1:9090\n")
    uvicorn.run(app, host="127.0.0.1", port=9090, log_level="warning")
