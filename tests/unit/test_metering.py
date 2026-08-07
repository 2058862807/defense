"""Unit tests for the metering / token-licensing store (C1)."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.metering.store import (
    InsufficientTokensError,
    MeteringStore,
    NoEntitlementError,
    OutOfTokensError,
)
from app.metering import service
from app.integrations.webhooks import (
    compute_signature,
    register_webhook,
    verify_signature,
    _canonical_body,
)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_MASTER_KEY", "test-master-key-0123456789")
    return MeteringStore(db_path=str(tmp_path / "metering.db"))


def _pilot(store, pool=10):
    customer = store.register_customer("First CU", org_type="credit_union")
    grant = store.issue_pilot_grant(customer["id"], token_pool=pool, months=6)
    key = store.create_api_key(customer["id"], grant["id"], "prod")
    return customer, grant, key["api_key"]


def test_reserve_settle(store):
    _, grant, api_key = _pilot(store)
    res = store.authorize_reservation(api_key, endpoint="/v1/transactions/analyze", tokens=1)
    assert res["tokens_remaining"] == 9
    assert res["grant_id"] == grant["id"]

    settled = store.settle_reservation(res["reservation_id"], event_type="tx_analysis", decision="pass", score=0.31)
    assert settled["tokens_remaining"] == 9
    bal = store.grant_balance(grant["id"])
    assert bal["tokens_consumed"] == 1
    assert bal["tokens_reserved"] == 0
    assert bal["tokens_remaining"] == 9

    events = store.period_usage(service.period_start(days=1))
    assert any(e["id"] == settled["id"] for e in events)


def test_release_returns_tokens(store):
    _, grant, api_key = _pilot(store)
    res = store.authorize_reservation(api_key, endpoint="/v1/x", tokens=1)
    assert store.grant_balance(grant["id"])["tokens_remaining"] == 9
    store.release_reservation(res["reservation_id"])
    bal = store.grant_balance(grant["id"])
    assert bal["tokens_reserved"] == 0
    assert bal["tokens_consumed"] == 0
    assert bal["tokens_remaining"] == 10


def test_exhaustion_is_402(store):
    _, grant, api_key = _pilot(store, pool=2)
    store.authorize_reservation(api_key, endpoint="/v1/x", tokens=1)
    store.authorize_reservation(api_key, endpoint="/v1/x", tokens=1)
    with pytest.raises(OutOfTokensError) as exc:
        store.authorize_reservation(api_key, endpoint="/v1/x", tokens=1)
    assert exc.value.http_status == 402


def test_insufficient_is_402(store):
    _, grant, api_key = _pilot(store, pool=1)
    with pytest.raises(InsufficientTokensError) as exc:
        store.authorize_reservation(api_key, endpoint="/v1/x", tokens=5)
    assert exc.value.http_status == 402


def test_expired_grant_is_402(store):
    customer = store.register_customer("Late CU")
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    grant = store.issue_grant(customer["id"], token_pool=100, expires_at=expired, kind="pilot")
    key = store.create_api_key(customer["id"], grant["id"], "prod")
    with pytest.raises(OutOfTokensError) as exc:
        store.authorize_reservation(key["api_key"], endpoint="/v1/x", tokens=1)
    assert exc.value.http_status == 402


def test_unknown_key_is_403(store):
    with pytest.raises(NoEntitlementError) as exc:
        store.authorize_reservation("pk_live_bogus", endpoint="/v1/x", tokens=1)
    assert exc.value.http_status == 403


def test_revoked_key_is_403(store):
    _, grant, api_key = _pilot(store)
    key_row = store.verify_api_key(api_key)
    assert store.revoke_api_key(key_row["key_prefix"]) is True
    with pytest.raises(NoEntitlementError) as exc:
        store.authorize_reservation(api_key, endpoint="/v1/x", tokens=1)
    assert exc.value.http_status == 403


def test_webhook_signing_roundtrip(store):
    _, _, api_key = _pilot(store)
    customer = store.verify_api_key(api_key)["customer_id"]
    hook = register_webhook(customer, "https://cu.example.com/hook", ["tx.analyzed"])
    body = _canonical_body({"score": 0.31, "decision": "pass"})
    sig = compute_signature(hook["secret"], body)
    assert verify_signature(hook["secret"], body, sig)
    assert not verify_signature(hook["secret"], body + b"x", sig)
    assert not verify_signature("wrong-secret", body, sig)


def test_period_commitment_deterministic(store):
    _, grant, api_key = _pilot(store, pool=5)
    res1 = store.authorize_reservation(api_key, endpoint="/v1/x", tokens=1)
    store.settle_reservation(res1["reservation_id"], event_type="tx_analysis", decision="pass", score=0.2)
    since = service.period_start(days=1)
    c1 = service.period_commitment(store, since)
    c2 = service.period_commitment(store, since)
    assert c1 == c2
    assert c1["event_count"] == 1
    assert c1["tokens_consumed_total"] == 1

    res2 = store.authorize_reservation(api_key, endpoint="/v1/x", tokens=1)
    store.settle_reservation(res2["reservation_id"], event_type="tx_analysis", decision="pass", score=0.3)
    c3 = service.period_commitment(store, since)
    assert c3["commitment"] != c1["commitment"]
    assert c3["tokens_consumed_total"] == 2


def test_license_offer_shape(store):
    _, grant, _ = _pilot(store)
    offer = service.license_offer(store.get_grant(grant["id"]))
    assert offer["offer"] == "paid_license"
    assert offer["price"]["amount_cents"] > 0
    assert offer["grant_id"] == grant["id"]


def test_mark_paid_tops_up_pool(store):
    _, grant, _ = _pilot(store, pool=3)
    upgraded = store.mark_paid(grant["id"], purchase_order="PO-1234", added_tokens=997)
    assert upgraded["status"] == "paid"
    assert upgraded["token_pool"] == 1000


def test_metering_dependency_auth_flow():
    """End-to-end through the dependency factory: 401 -> 402 with offer."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from app.metering.deps import require_metered_key

    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "metering_dep_test.db")
    store = MeteringStore(db_path=tmp)
    customer = store.register_customer("Dep CU")
    grant = store.issue_pilot_grant(customer["id"], token_pool=1, months=6)
    key = store.create_api_key(customer["id"], grant["id"], "dep")
    api_key = key["api_key"]

    app = FastAPI()

    @app.post("/v1/check")
    def check(mk=Depends(require_metered_key(1, store=store))):
        return {"reservation_id": mk.reservation["reservation_id"]}

    c = TestClient(app, base_url="http://app.protean.sh", raise_server_exceptions=False)
    assert c.post("/v1/check").status_code == 401
    r = c.post("/v1/check", headers={"X-API-Key": api_key})
    assert r.status_code == 200

    # second call - pool exhausted -> 402
    r2 = c.post("/v1/check", headers={"X-API-Key": api_key})
    assert r2.status_code == 402
    assert r2.headers.get("X-Protean-Entitlement") == "pilot_exhausted"
    assert "offer" in str(r2.json())
