import json
import hashlib

import pytest

from app.evm.fairness_registry import trans_verify_explanation


@pytest.fixture
def package():
    return {
        "score": 0.8597,
        "explanation": {
            "input": [2.0, 20.0, 1.0, 0.0, 0.0, 0.5, 50.0],
            "shap_values": [0.41, 0.28, -0.13, 0.09, 0.05, -0.02, 0.01],
            "base_value": 0.5,
            "model_hash": "9843c560d965d7c071051fcc92ed4d72c3f3eaf0e91bd64481b2e6497c1ed472",
        },
        "commitments": {
            "model_commitment": "9843c560d965d7c071051fcc92ed4d72c3f3eaf0e91bd64481b2e6497c1ed472",
            "input_commitment": "input123",
            "score_commitment": "score123",
            "shap_commitment": "shap123",
            "combined_commitment": "combined123",
        },
    }


def canonical(package):
    explanation = package["explanation"]
    model = explanation["model_hash"]
    f = json.dumps(explanation["input"], sort_keys=True, separators=(",", ":")).encode()
    s = json.dumps(package["score"], sort_keys=True).encode()
    sh = json.dumps(explanation["shap_values"], sort_keys=True, separators=(",", ":")).encode()
    return {
        "input_commitment": hashlib.sha256(f).hexdigest(),
        "score_commitment": hashlib.sha256(s).hexdigest(),
        "shap_commitment": hashlib.sha256(sh).hexdigest(),
        "combined_commitment": hashlib.sha256(model.encode() + f + s + sh).hexdigest(),
    }


def test_recompute_matches_production_serializer(package):
    """trans_verify must reproduce xai.create_commitments byte-for-byte."""
    expected = canonical(package)
    result = trans_verify_explanation(package)
    recomputed = result["recomputed"]
    assert recomputed["input_commitment"] == expected["input_commitment"]
    assert recomputed["score_commitment"] == expected["score_commitment"]
    assert recomputed["shap_commitment"] == expected["shap_commitment"]
    assert recomputed["combined_commitment"] == expected["combined_commitment"]
    assert recomputed["model_commitment"] == package["commitments"]["model_commitment"]


def test_anchored_ok_with_consistent_commitments(package):
    expected = canonical(package)
    package["commitments"].update(expected)
    result = trans_verify_explanation(package)
    assert result["anchored_ok"] is True
    assert all(result["matches"].values())


def test_tampered_shap_breaks_anchor(package):
    expected = canonical(package)
    package["commitments"].update(expected)
    package["explanation"]["shap_values"][0] = 0.99
    result = trans_verify_explanation(package)
    assert result["anchored_ok"] is False
    assert result["matches"]["shap_commitment"] is False
    assert result["matches"]["combined_commitment"] is False


def test_tampered_score_breaks_anchor(package):
    expected = canonical(package)
    package["commitments"].update(expected)
    package["score"] = 0.1
    result = trans_verify_explanation(package)
    assert result["anchored_ok"] is False
    assert result["matches"]["combined_commitment"] is False


def test_missing_model_hash_raises(package):
    package["commitments"] = {}
    package["explanation"] = {}
    with pytest.raises(ValueError):
        trans_verify_explanation(package)
