"""Signer key rotation tool tests (scripts/rotate_signer_keys.py).

Covers the fail-closed guards (no master key, undecryptable store, EVM
pre-migration timing), dry-run no-op, live Flashbots rotation with encrypted
archive + pilot store + ledger, split-identity, and key-restricted updates.
"""
import importlib.util
import json
from pathlib import Path

import pytest
from eth_account import Account

from app.core.ledger import HashChainedLedger
from app.core.pilot_secrets import PILOT_CREDENTIALS
from app.core.secrets_store import SecretsStore

MASTER = "rotation-test-master-key-0123456789"
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rotate_signer_keys.py"


@pytest.fixture()
def rot(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("rotate_signer_keys", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    monkeypatch.setenv("SECRETS_MASTER_KEY", MASTER)
    monkeypatch.setattr(mod, "LOCAL_SECRETS", tmp_path / "local_secrets.env")
    monkeypatch.setattr(mod, "STORE_PATH", tmp_path / "secrets.enc")
    monkeypatch.setattr(mod, "MASTER_KEY_FILE", tmp_path / ".secrets_master_key")
    monkeypatch.setattr(mod, "DEFAULT_BACKUP_DIR", tmp_path / "rotations")

    store = SecretsStore(path=str(tmp_path / "secrets.enc"), master_key=MASTER)
    store.touch()

    ledger = HashChainedLedger(db_path=str(tmp_path / "ledger.db"))
    monkeypatch.setattr("app.core.ledger.ledger", ledger)

    env_path = tmp_path / "local_secrets.env"
    evm, fb = Account.create(), Account.create()
    env_path.write_text(
        "# local signer keys\n"
        f"EVM_PRIVATE_KEY={evm.key.hex()}\n"
        f"FLASHBOTS_SIGNING_KEY={fb.key.hex()}\n"
    )
    return {"mod": mod, "tmp": tmp_path, "env_path": env_path,
            "store": store, "ledger": ledger, "evm": evm, "fb": fb}


def run(mod, *args, monkeypatch):
    monkeypatch.setattr("sys.argv", ["rotate_signer_keys.py", *args])
    return mod.main()


def current(rot):
    text = rot["env_path"].read_text()
    out = {}
    for line in text.splitlines():
        if line.startswith("EVM_PRIVATE_KEY="):
            out["evm"] = line.split("=", 1)[1]
        if line.startswith("FLASHBOTS_SIGNING_KEY="):
            out["fb"] = line.split("=", 1)[1]
    return out


def test_noop_without_targets(rot, monkeypatch):
    assert run(rot["mod"], monkeypatch=monkeypatch) == 1
    assert current(rot)["evm"] == rot["evm"].key.hex()
    assert current(rot)["fb"] == rot["fb"].key.hex()


def test_fails_closed_without_master_key(rot, monkeypatch):
    monkeypatch.delenv("SECRETS_MASTER_KEY", raising=False)
    rc = run(rot["mod"], "--rotate-flashbots", monkeypatch=monkeypatch)
    assert rc == 1
    assert current(rot)["fb"] == rot["fb"].key.hex()


def test_evm_rotation_refused_pre_migration(rot, monkeypatch):
    rc = run(rot["mod"], "--rotate-evm", monkeypatch=monkeypatch)
    assert rc == 1
    assert current(rot)["evm"] == rot["evm"].key.hex()


def test_evm_rotation_allowed_when_ownership_moved(rot, monkeypatch):
    mod = rot["mod"]
    monkeypatch.setattr(mod, "onchain_owner", lambda rpc, reg: Account.create().address)
    rc = run(
        mod,
        "--rotate-evm", "--yes", "--out", str(rot["tmp"] / "r.json"),
        "--rpc-url", "http://rpc", "--registry", "0x0000000000000000000000000000000000000001",
        monkeypatch=monkeypatch,
    )
    assert rc == 0
    after = current(rot)
    assert after["evm"] != rot["evm"].key.hex()
    assert after["fb"] == rot["fb"].key.hex()


def test_evm_rotation_refused_when_still_owner(rot, monkeypatch):
    mod = rot["mod"]
    monkeypatch.setattr(mod, "onchain_owner", lambda rpc, reg: rot["evm"].address)
    rc = run(
        mod, "--rotate-evm", "--yes",
        "--rpc-url", "http://rpc", "--registry", "0x0000000000000000000000000000000000000001",
        monkeypatch=monkeypatch,
    )
    assert rc == 1
    assert current(rot)["evm"] == rot["evm"].key.hex()

def test_dry_run_writes_nothing(rot, monkeypatch):
    mod = rot["mod"]
    before = rot["env_path"].read_text()
    rc = run(mod, "--rotate-flashbots", "--dry-run", monkeypatch=monkeypatch)
    assert rc == 0
    assert rot["env_path"].read_text() == before
    assert rot["store"].list_paths() == []
    assert rot["ledger"].verify_chain()["ok"] is True
    assert not rot["ledger"].recent(limit=5)


def test_flashbots_rotation_live(rot, monkeypatch):
    mod = rot["mod"]
    out_json = rot["tmp"] / "r.json"
    rc = run(mod, "--rotate-flashbots", "--yes", "--out", str(out_json),
             monkeypatch=monkeypatch)
    assert rc == 0

    after = current(rot)
    assert after["fb"] != rot["fb"].key.hex()
    assert after["evm"] == rot["evm"].key.hex()  # EVM untouched

    new_fb = Account.from_key(after["fb"])
    assert new_fb.address != rot["evm"].address  # split identity

    # encrypted archive retains the retired key (readable only via the store)
    archives = [p for p in rot["store"].list_paths() if "secret/rotate/archive/" in p]
    assert len(archives) == 1
    archived = rot["store"].get(archives[0])
    assert archived["private_key"] == rot["fb"].key.hex()
    assert archived["address"] == rot["fb"].address

    # pilot store updated with the new key
    pstore_pilot = PILOT_CREDENTIALS["flashbots_signing_key"][0]
    from app.core.pilot_secrets import PilotSecretsStore
    p = PilotSecretsStore(store=rot["store"]).get("flashbots_signing_key")
    assert p == after["fb"]

    # plaintext backup written for rollback
    backups = list((rot["tmp"] / "rotations").glob("local_secrets_*.env"))
    assert len(backups) == 1
    assert rot["fb"].key.hex() in backups[0].read_text()

    # ledger carries addresses only - never key material
    entries = [e for e in rot["ledger"].recent(limit=5) if e["event_type"] == "SIGNER_ROTATE"]
    assert len(entries) == 1
    payload = entries[0]["payload"]
    rotated = payload["rotated"]["flashbots_signing_key"]
    assert rotated["old_address"] == rot["fb"].address
    assert rotated["new_address"] == new_fb.address
    assert rotated["new_address"] != rot["fb"].address
    assert after["fb"] not in json.dumps(payload)  # no key material
    assert rot["fb"].key.hex() not in json.dumps(payload)

    # report JSON is addresses-only
    report = json.loads(out_json.read_text())
    assert after["fb"] not in json.dumps(report)
    assert report["rotated"]["flashbots_signing_key"]["new_address"] == new_fb.address


def test_rotation_uses_fresh_random_keys(rot, monkeypatch):
    mod = rot["mod"]
    first = run(mod, "--rotate-flashbots", "--yes", "--out", str(rot["tmp"] / "a.json"),
                monkeypatch=monkeypatch)
    assert first == 0
    after1 = current(rot)["fb"]
    second = run(mod, "--rotate-flashbots", "--yes", "--out", str(rot["tmp"] / "b.json"),
                 monkeypatch=monkeypatch)
    assert second == 0
    after2 = current(rot)["fb"]
    assert after1 != after2  # two rotations must never collide
