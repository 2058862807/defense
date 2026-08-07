"""B8 address-risk screening engine tests.

Covers: shadow-set exact match (block), OFAC SDN digital-currency-address match
(block), FATF high-risk jurisdiction (review), currency flag (review), large
transaction (review), clean address (allow), provider stubs (not configured,
neutral), and the fail-closed policy ordering.
"""

import json
import unittest.mock as mock

import pytest

from app.compliance.address_risk import (
    AddressRiskEngine,
    normalize_address,
)

TEST_ADDR = "0x1111111111111111111111111111111111111111"
SANCTIONED = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture()
def engine(tmp_path):
    shadow = tmp_path / "shadow.json"
    shadow.write_text(json.dumps({
        "addresses": [{"address": SANCTIONED, "label": "test sanctioned", "list": "shadow"}],
        "jurisdictions": {"high": ["ZZ"], "grey": []},
        "currencies": {"blocked": [{"ticker": "XMR", "reason": "privacy"}], "flagged": []},
    }))
    eng = AddressRiskEngine(
        shadow_path=str(shadow),
        review_threshold=40.0,
        block_threshold=90.0,
        large_txn_review_usd=10000.0,
    )
    return eng


def test_normalize_address():
    mixed = "0x" + ("a" * 20) + ("B" * 20)
    assert normalize_address(mixed) == "0x" + "a" * 20 + "b" * 20
    assert normalize_address("0x123") is None
    assert normalize_address("") is None


def test_shadow_match_blocks(engine):
    result = engine.screen_transaction(SANCTIONED)
    assert result["decision"] == "block"
    assert result["risk_score"] == 100.0
    assert result["shadow_match"]["label"] == "test sanctioned"
    assert "shadow" in result["sources"]


def test_ofac_address_match_blocks(engine):
    fake_ofac = mock.Mock()
    fake_ofac.get_sdn_list.return_value = [
        {
            "sdn_name": "TEST CO LTD",
            "ent_num": "9999",
            "program": "SDGT",
            "addresses": [TEST_ADDR],
        }
    ]
    engine.ofac = fake_ofac
    result = engine.screen_transaction(TEST_ADDR)
    assert result["decision"] == "block"
    assert result["ofac_address_match"]["sdn_name"] == "TEST CO LTD"
    assert "ofac-sdn" in result["sources"]


def test_high_risk_jurisdiction_review(engine, monkeypatch):
    monkeypatch.setattr(engine.fatf, "is_high_risk", lambda j: {
        "high_risk": True, "list": "FATF Black List", "risk_level": "high", "requires_edd": True,
    })
    result = engine.screen_transaction(TEST_ADDR, jurisdiction="Iran")
    assert result["decision"] == "review"
    assert result["risk_score"] >= 40.0
    assert result["jurisdiction_risk"]["risk_level"] == "high"
    assert "fatf" in result["sources"]


def test_shadow_currency_flag_review(engine, monkeypatch):
    monkeypatch.setattr(engine.fatf, "is_high_risk", lambda j: {"high_risk": False})
    result = engine.screen_transaction(TEST_ADDR, currency="XMR")
    assert result["decision"] == "review"
    assert result["currency_flag"]["action"] == "blocked"
    assert "shadow-currency" in result["sources"]


def test_large_transaction_review(engine, monkeypatch):
    monkeypatch.setattr(engine.fatf, "is_high_risk", lambda j: {"high_risk": False})
    result = engine.screen_transaction(TEST_ADDR, amount=50000.0)
    assert result["decision"] == "review"
    assert "amount" in result["sources"]


def test_clean_address_allows(engine, monkeypatch):
    monkeypatch.setattr(engine.fatf, "is_high_risk", lambda j: {"high_risk": False})
    result = engine.screen_transaction(TEST_ADDR, amount=100.0)
    assert result["decision"] == "allow"
    assert result["risk_score"] < engine.review_threshold


def test_invalid_address_errors(engine):
    result = engine.screen_transaction("not-an-address")
    assert result["decision"] == "error"
    assert result["error"]


def test_providers_not_configured_neutral(engine):
    assert all(not p.configured for p in engine.providers)
    result = engine.screen_transaction(TEST_ADDR, amount=5.0)
    assert all(a["risk_score"] == 0.0 for a in result["analytics"])
    assert all(a["configured"] is False for a in result["analytics"])


def test_missing_shadow_file_logs_and_allows_clean(engine, tmp_path, monkeypatch, caplog):
    engine.shadow_path = str(tmp_path / "does-not-exist.json")
    engine._shadow = None
    monkeypatch.setattr(engine.fatf, "is_high_risk", lambda j: {"high_risk": False})
    result = engine.screen_transaction(TEST_ADDR, amount=1.0)
    assert result["decision"] == "allow"
    assert any("SHADOW SANCTIONS SET MISSING" in r.message for r in caplog.records)
