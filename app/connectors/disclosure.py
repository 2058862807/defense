"""
Tiered Disclosure - Customer, Regulator, Audit Views
GAP8: Complete tiered disclosure

- Customer view: risk score, action, onchain hash, no SHAP details, no raw proof
- Regulator view: full ZK package, commitments, SHAP values, fairness reasons, policy version, provenance
- Audit view: everything + training data hash, model hash, circuit hash, SLSA provenance, QRNG provider, HSM provider, OFAC/FATF source live/cached
"""

from typing import Dict, Any, Literal
import logging

logger = logging.getLogger(__name__)

def get_tiered_view(zk_package: Dict[str, Any], view: Literal["customer", "regulator", "audit"] = "customer") -> Dict[str, Any]:
    """
    Return tiered disclosure view of ZK XAI package
    """
    if view == "audit":
        # Audit sees everything
        return zk_package

    elif view == "regulator":
        # Regulator sees full ZK package but not ultra-sensitive provenance like QRNG/HSM internal counters
        return {
            "score": zk_package.get("score"),
            "action": zk_package.get("action") or ("PROTECT_PRIVATE" if zk_package.get("score", 0) > 0.7 else "ALLOW_PUBLIC"),
            "onchain_hash": zk_package.get("onchain_hash"),
            "commitments": zk_package.get("commitments"),
            "explanation": {
                "shap_values": zk_package.get("explanation", {}).get("shap_values"),
                "feature_names": zk_package.get("explanation", {}).get("feature_names"),
                "top_feature": max(
                    zip(
                        zk_package.get("explanation", {}).get("feature_names", []),
                        zk_package.get("explanation", {}).get("shap_values", [])
                    ),
                    key=lambda x: abs(x[1]) if not isinstance(x[1], list) else 0,
                    default=("unknown", 0)
                )[0] if zk_package.get("explanation", {}).get("feature_names") else "unknown"
            },
            "fairness": zk_package.get("fairness"),
            "policy_version": zk_package.get("fairness", {}).get("policy_version") or zk_package.get("provenance", {}).get("policy_version"),
            "provenance": {
                "model_hash": zk_package.get("provenance", {}).get("model_hash") or zk_package.get("metadata", {}).get("model_hash"),
                "policy_version": zk_package.get("provenance", {}).get("policy_version"),
            }
        }

    else:  # customer
        # Customer view: minimal, no SHAP details, no raw proof
        score = zk_package.get("score", 0)
        action = zk_package.get("action") or ("PROTECT_PRIVATE" if score > 0.7 else "ALLOW_PUBLIC")
        
        if score > 0.7:
            customer_message = f"Your transaction was protected via private mempool due to high MEV risk. MEV risk score {score:.2f}. On-chain proof anchored at {zk_package.get('onchain_hash','')[:10]}..."
        else:
            customer_message = f"Your transaction was allowed via public mempool. MEV risk score {score:.2f} low. Proof logged for audit."

        return {
            "score": score,
            "action": action,
            "onchain_hash": zk_package.get("onchain_hash"),
            "customer_message": customer_message,
            "risk_level": "high" if score > 0.7 else "low" if score < 0.3 else "medium"
        }

def get_disclosure_tiers_definition() -> Dict[str, Any]:
    return {
        "customer": {
            "description": "Customer view - risk score, action, onchain hash, no SHAP, no raw proof, customer-friendly message",
            "fields": ["score", "action", "onchain_hash", "customer_message", "risk_level"],
            "example": {
                "score": 0.85,
                "action": "PROTECT_PRIVATE",
                "onchain_hash": "0xabc123...",
                "customer_message": "Your transaction was protected via private mempool due to high MEV risk.",
                "risk_level": "high"
            }
        },
        "regulator": {
            "description": "Regulator view - full ZK package, commitments, SHAP, fairness reasons, policy version, no ultra-sensitive provenance",
            "fields": ["score", "action", "onchain_hash", "commitments", "explanation", "fairness", "policy_version", "provenance.model_hash"],
            "example": {
                "score": 0.85,
                "action": "PROTECT_PRIVATE",
                "onchain_hash": "0xabc...",
                "commitments": {"model_commitment": "9843c560...", "input_commitment": "abc..."},
                "explanation": {"shap_values": [0.1, 0.2], "feature_names": ["gas", "value"], "top_feature": "slippage_bps"},
                "fairness": {"is_fair": True, "reasons": ["Fair per policy v1.2.0"], "policy_version": "1.2.0"}
            }
        },
        "audit": {
            "description": "Audit view - everything + training hash, model hash, circuit hash, SLSA, QRNG provider, HSM provider, OFAC/FATF source",
            "fields": ["* - full zk_package + provenance.training_data_hash + provenance.circuit_hash + provenance.qrng_provider + provenance.hsm_provider + provenance.ofac_source + provenance.fatf_source"],
            "example": {
                "score": 0.85,
                "metadata": {"model_hash": "9843c560...", "training_data_hash": "1325..."},
                "commitments": {"model_commitment": "9843c560..."},
                "explanation": {"shap_values": [...], "feature_names": [...]},
                "fairness": {"is_fair": True, "reasons": [...], "policy_version": "1.2.0"},
                "provenance": {
                    "model_hash": "9843c560...",
                    "training_data_hash": "1325...",
                    "circuit_hash": "d80e3987...",
                    "qrng_provider": "Qrypt",
                    "hsm_provider": "AWS CloudHSM",
                    "ofac_source": "live treasury.gov",
                    "fatf_source": "live fatf-gafi.org",
                    "slsa_level": "L3"
                },
                "zk_proof": {"pi_a": [...], "pi_b": [...], "pi_c": [...]},
                "onchain_hash": "0xabc..."
            }
        }
    }
