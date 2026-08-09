"""KMS rotation persistence: every rotation is appended to the hash-chained
ledger and survives restart (durable, independently verifiable)."""

import tempfile
from pathlib import Path

from app.core.ledger import HashChainedLedger
from app.kms.manager import KMSManagerEnterprise


def _make(tmp: Path):
    return HashChainedLedger(db_path=str(tmp / "ledger.db"))


def test_manual_rotation_writes_durable_ledger_entry():
    with tempfile.TemporaryDirectory() as d:
        ledger = _make(Path(d))
        kms = KMSManagerEnterprise(ledger=ledger)
        res = kms.rotate_now(trigger="manual")

        entries = ledger.recent(limit=10)
        rotate_entries = [e for e in entries if e["event_type"] == "KMS_ROTATE"]
        assert len(rotate_entries) >= 1
        latest = rotate_entries[0]
        assert latest["status"] == "SUCCESS"
        assert latest["payload"]["key_id"] == res["new_key_id"]
        assert latest["payload"]["fingerprint"] == res["fingerprint"]
        assert latest["payload"]["event_hash"] == res["event_hash"]
        assert latest["payload"]["trigger"] == "manual"
        assert latest["payload"]["active_count"] == 1

        # Durability: a brand-new process opening the same db still sees it.
        ledger2 = _make(Path(d))
        again = [e for e in ledger2.recent(limit=10) if e["event_type"] == "KMS_ROTATE"]
        assert len(again) >= 1
        assert again[0]["payload"]["event_hash"] == res["event_hash"]

        # Hash chain is intact end-to-end.
        assert ledger2.verify_chain()["ok"] is True


def test_ttl_rotation_records_trigger():
    with tempfile.TemporaryDirectory() as d:
        ledger = _make(Path(d))
        kms = KMSManagerEnterprise(ttl_seconds=0, ledger=ledger)
        kms.ensure_keys()  # issues a key under expired-TTL policy -> "ttl"
        entries = [e for e in ledger.recent(limit=10) if e["event_type"] == "KMS_ROTATE"]
        assert entries and entries[0]["payload"]["trigger"] in ("ttl", "startup")
        assert entries[0]["payload"]["active_count"] >= 1


def test_rotate_retires_old_and_new_active_single():
    with tempfile.TemporaryDirectory() as d:
        kms = KMSManagerEnterprise(ledger=_make(Path(d)))
        first = kms.rotate_now()
        second = kms.rotate_now()
        assert first["new_key_id"] != second["new_key_id"]
        keys = kms.list_keys()
        active = [k for k in keys if k["status"] == "active"]
        assert len(active) == 1
        assert active[0]["id"] == second["new_key_id"]
