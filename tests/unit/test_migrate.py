"""Migration-bridge tests (C1 -> legacy license/connector surfaces)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.metering import migrate
from app.metering.store import (
    EntitlementError,
    MeteringStore,
    NoEntitlementError,
    OutOfTokensError,
)
from app.connectors import usage as usage_tracker


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_MASTER_KEY", "test-master-key-0123456789")
    return MeteringStore(db_path=str(tmp_path / "metering.db"))


def _license(tier="enterprise_gov", license_id="gov-enterprise-test-001", days=365, per_day=10000):
    expiry = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    return {
        "license_id": license_id,
        "tier": tier,
        "customer": "DOJ",
        "features": {
            "offense": {"enabled": True, "max_profit_eth_per_day": 100},
            "defense": {"enabled": True, "max_protected_txs_per_day": per_day},
            "connector": {"enabled": True, "qps": 100},
        },
        "expiry": expiry,
    }


def _provisioned(store, tier="enterprise_gov", **kw):
    lic = _license(tier=tier, **kw)
    grant = migrate.ensure_grant_for_license(lic, store=store)
    key = store.create_api_key(grant["customer_id"], grant["id"], "connector")
    return lic, grant, key["api_key"]


# ------------------------------------------------------------------ #
# License file -> metering grant
# ------------------------------------------------------------------ #
def test_tokens_for_license_derives_from_allowance_and_term(store):
    lic = _license(days=365)
    assert migrate.tokens_for_license(lic) == 10000 * 365


def test_ensure_grant_idempotent_and_keyed_by_license_id(store):
    lic = _license()
    g1 = migrate.ensure_grant_for_license(lic, store=store)
    g2 = migrate.ensure_grant_for_license(lic, store=store)
    assert g1["id"] == g2["id"]
    assert g1["purchase_order"] == "gov-enterprise-test-001"
    assert g1["kind"] == "licensed"
    assert g1["tier"] == "enterprise_gov"
    assert g1["token_pool"] == 10000 * 365


def test_ensure_grant_never_remints_tokens_after_consumption(store):
    lic, grant, api_key = _provisioned(store, days=1)
    del grant
    store.authorize_reservation(api_key, "/v1/protect", tokens=1)
    again = migrate.ensure_grant_for_license(lic, store=store)
    assert again["tokens_reserved"] == 1


def test_renew_grant_extends_expiry(store):
    lic, grant, _ = _provisioned(store, days=30)
    renewed = _license(days=400)
    renewed["license_id"] = lic["license_id"]
    out = migrate.renew_grant_for_license(renewed, store=store)
    assert out["id"] == grant["id"]
    assert out["expires_at"] > grant["expires_at"]


def test_ensure_grant_raises_without_license_id(store):
    with pytest.raises(EntitlementError):
        migrate.ensure_grant_for_license({"tier": "dev"}, store=store)


# ------------------------------------------------------------------ #
# metered_authorize (connector path)
# ------------------------------------------------------------------ #
def test_metered_authorize_reserves_and_feature_gates(store):
    _, grant, api_key = _provisioned(store)
    res = migrate.metered_authorize(api_key, "/connector/defense", feature="defense", store=store)
    assert res["grant_id"] == grant["id"]
    assert res["tokens"] == 1
    store.settle_reservation(res["reservation_id"], decision="pass")

    # enterprise_gov is licensed for all connector features (offense too)
    res2 = migrate.metered_authorize(api_key, "/connector/offense", feature="offense", store=store)
    assert res2["tokens"] == 1
    store.release_reservation(res2["reservation_id"])


def test_metered_authorize_dev_cannot_use_offense(store):
    _, _, api_key = _provisioned(store, tier="dev")
    migrate.metered_authorize(api_key, "/connector/defense", feature="defense", store=store)
    with pytest.raises(EntitlementError):
        migrate.metered_authorize(api_key, "/connector/offense", feature="offense", store=store)


def test_metered_authorize_exhaustion(store):
    _, _, api_key = _provisioned(store, days=1, per_day=1)
    migrate.metered_authorize(api_key, "/x", feature="defense", store=store)
    with pytest.raises(OutOfTokensError):
        migrate.metered_authorize(api_key, "/x", feature="defense", store=store)


def test_metered_authorize_unknown_key(store):
    with pytest.raises(NoEntitlementError):
        migrate.metered_authorize("pk_live_bogus", "/x", store=store)


# ------------------------------------------------------------------ #
# usage_tracker compatibility surface
# ------------------------------------------------------------------ #
def test_record_usage_writes_zero_token_event_without_charge(store):
    _, grant, api_key = _provisioned(store)
    rec = usage_tracker.record_usage(api_key, "/v1/protect", latency_ms=12.0, status=200, store=store)
    assert rec["recorded"] is True
    bal = store.grant_balance(grant["id"])
    assert bal["tokens_consumed"] == 0
    events = store.all_usage()
    assert any(e["event_type"] == "api_call" and e["tokens"] == 0 for e in events)


def test_record_usage_unknown_key_logs_only(store):
    rec = usage_tracker.record_usage("pk_live_nope", "/v1/protect", 1.0, 200, store=store)
    assert rec["recorded"] is False


def test_get_usage_stats_empty_shape(store):
    stats = usage_tracker.get_usage_stats(store=store)
    assert stats["total_requests"] == 0
    assert stats["success_rate"] == 0


def test_get_usage_stats_after_settle(store):
    _, _, api_key = _provisioned(store)
    res = store.authorize_reservation(api_key, "/v1/protect", tokens=1)
    store.settle_reservation(res["reservation_id"], event_type="connector_analysis", decision="pass")
    stats = usage_tracker.get_usage_stats(api_key=api_key, store=store)
    assert stats["total_requests"] == 1
    assert stats["success"] == 1
    assert stats["per_endpoint"].get("/v1/protect") == 1


def test_get_customer_usage_aggregates_tokens(store):
    lic, grant, api_key = _provisioned(store)
    res = store.authorize_reservation(api_key, "/v1/protect", tokens=1)
    store.settle_reservation(res["reservation_id"], decision="pass")
    usage = usage_tracker.get_customer_usage(lic["customer"], store=store)
    assert usage["tier"] == "enterprise_gov"
    assert usage["tokens_consumed"] == 1
    assert usage["tokens_remaining"] == grant["token_pool"] - 1
    assert usage["grants"] == 1


def test_check_rate_limit_funded_then_exhausted(store):
    _, _, api_key = _provisioned(store, days=1, per_day=1)
    assert usage_tracker.check_rate_limit(api_key, store=store) is True
    store.authorize_reservation(api_key, "/x", tokens=1)
    assert usage_tracker.check_rate_limit(api_key, store=store) is False


def test_check_rate_limit_unknown_key(store):
    assert usage_tracker.check_rate_limit("pk_live_bogus", store=store) is False


# ------------------------------------------------------------------ #
# Connector FastAPI dependency (HTTP status mapping)
# ------------------------------------------------------------------ #
def test_connector_dependency_maps_entitlement_to_http(store, monkeypatch):
    import app.connectors.enterprise_connector as connector

    monkeypatch.setattr(connector, "metered_authorize", lambda *a, **kw: migrate.metered_authorize(*a, **kw, store=store))

    dep = connector.verify_license_feature("defense")
    _, grant, api_key = _provisioned(store, days=1, per_day=1)

    res = dep(x_api_key=api_key)
    assert res["grant_id"] == grant["id"]
    store.release_reservation(res["reservation_id"])

    store.authorize_reservation(api_key, "/v1/protect", tokens=1)
    with pytest.raises(HTTPException) as exc:
        dep(x_api_key=api_key)
    assert exc.value.status_code == 402


def test_licensing_server_health_smoke():
    from fastapi.testclient import TestClient
    from app.licensing.server import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["metering"] == "store-backed"
