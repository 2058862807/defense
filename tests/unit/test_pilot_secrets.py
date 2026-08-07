"""Pilot credential store + admin router + address-risk provider wiring tests."""
import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.pilot_secrets import PILOT_CREDENTIALS, PilotSecretsStore, pilot_secrets
from app.core.secrets_store import SecretsStore


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_MASTER_KEY", "pilot-test-master-key-0123456789")
    return SecretsStore(path=str(tmp_path / "secrets.enc"), master_key="pilot-test-master-key-0123456789")


@pytest.fixture()
def pstore(store):
    return PilotSecretsStore(store=store)


def test_all_eleven_fields_registered():
    assert len(PILOT_CREDENTIALS) == 11
    for field, (env_var, label) in PILOT_CREDENTIALS.items():
        assert env_var, f"{field} missing env var"
        assert label


def test_set_get_delete_roundtrip(pstore):
    pstore.set("chainalysis_api_token", "tok_abc")
    assert pstore.get("chainalysis_api_token") == "tok_abc"
    assert pstore.status("chainalysis_api_token")["source"] == "store"
    assert pstore.delete("chainalysis_api_token") is True
    assert pstore.get("chainalysis_api_token") is None
    assert pstore.status("chainalysis_api_token")["configured"] is False


def test_unknown_field_rejected(pstore):
    with pytest.raises(KeyError):
        pstore.set("bogus_field", "x")
    assert pstore.get("bogus_field") is None
    with pytest.raises(KeyError):
        pstore.status("bogus_field")
    with pytest.raises(KeyError):
        pstore.delete("bogus_field")


def test_empty_value_rejected(pstore):
    with pytest.raises(ValueError):
        pstore.set("trm_api_token", "")


def test_env_var_wins_over_store(pstore, monkeypatch):
    pstore.set("trm_api_token", "stored_val")
    monkeypatch.setenv("TRM_API_TOKEN", "env_val")
    assert pstore.get("trm_api_token") == "env_val"
    assert pstore.status("trm_api_token")["source"] == "env"


def test_snapshot_shape(pstore):
    snap = pstore.snapshot()
    assert len(snap) == len(PILOT_CREDENTIALS)
    for entry in snap:
        assert set(entry.keys()) == {"field", "env_var", "label", "configured", "source"}
        assert "value" not in entry


def test_refresh_is_fail_open(pstore):
    pstore.refresh()


def test_chainalysis_provider_configured_flip(pstore, monkeypatch):
    monkeypatch.setattr("app.core.pilot_secrets.pilot_secrets", pstore)
    from app.compliance.address_risk import ChainalysisSanctionsProvider
    p = ChainalysisSanctionsProvider()
    assert p.configured is False
    pstore.set("chainalysis_api_token", "tok_x")
    assert p.configured is True
    res = p.screen_address("0x0000000000000000000000000000000000000001")
    assert res["configured"] is True


def test_trm_provider_configured_flip(pstore, monkeypatch):
    monkeypatch.setattr("app.core.pilot_secrets.pilot_secrets", pstore)
    from app.compliance.address_risk import TrmRiskScreeningProvider
    p = TrmRiskScreeningProvider()
    assert p.configured is False
    pstore.set("trm_api_token", "tok_y")
    assert p.configured is True
    res = p.screen_address("0x0000000000000000000000000000000000000002")
    assert res["configured"] is True


def test_unconfigured_screening_is_neutral(pstore):
    from app.compliance.address_risk import address_risk_engine
    res = address_risk_engine.screen_transaction("0x0000000000000000000000000000000000000001")
    assert res["decision"] == "allow"
    assert res["analytics"]
    for a in res["analytics"]:
        assert a["configured"] is False


def test_status_no_secret_leakage(pstore):
    pstore.set("aws_secret_access_key", "super-secret-value")
    from app.compliance.address_risk import address_risk_engine
    for p in address_risk_engine.status():
        assert "configured" in p
        assert "secret" not in p
        assert "token" not in p


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_MASTER_KEY", "pilot-test-master-key-0123456789")
    monkeypatch.setenv("SECRETS_STORE_PATH", str(tmp_path / "secrets.enc"))
    from app.core.config import settings
    monkeypatch.setattr(settings, "env", "dev")
    from app.core.pilot_secrets import pilot_secrets
    monkeypatch.setattr(
        pilot_secrets,
        "store",
        SecretsStore(path=str(tmp_path / "secrets.enc"), master_key="pilot-test-master-key-0123456789"),
    )
    from fastapi import FastAPI
    from app.core.pilot_router import router as pilot_router
    mini = FastAPI()
    mini.include_router(pilot_router)
    return TestClient(mini)


def test_router_requires_no_token_dev(client):
    r = client.get("/pilot/credentials")
    assert r.status_code == 200


def test_router_set_refresh_status_delete(client):
    r = client.post("/pilot/credentials/chainalysis_api_token", json={"value": "tok_rt"})
    assert r.status_code == 200
    body = r.json()["updated"]
    assert body["configured"] is True
    assert body["source"] == "store"

    r = client.post("/pilot/credentials/refresh")
    assert r.status_code == 200
    assert r.json()["status"] == "refreshed"

    r = client.get("/pilot/status")
    assert r.status_code == 200
    j = r.json()
    assert "integrations" in j and "credentials" in j
    assert j["credentials"]["chainalysis_api_token"]["configured"] is True

    r = client.delete("/pilot/credentials/chainalysis_api_token")
    assert r.status_code == 200
    assert r.json()["removed"] is True

    r = client.get("/pilot/status")
    assert r.json()["credentials"]["chainalysis_api_token"]["configured"] is False


def test_router_unknown_field_404(client):
    r = client.post("/pilot/credentials/bogus", json={"value": "x"})
    assert r.status_code == 404
    r = client.delete("/pilot/credentials/bogus")
    assert r.status_code == 404


def test_router_requires_value(client):
    r = client.post("/pilot/credentials/trm_api_token", json={})
    assert r.status_code == 422


def test_router_never_echoes_value(client):
    client.post("/pilot/credentials/aws_secret_access_key", json={"value": "s3cr3t"})
    r = client.get("/pilot/credentials")
    assert "s3cr3t" not in r.text
    r = client.get("/pilot/status")
    assert "s3cr3t" not in r.text
