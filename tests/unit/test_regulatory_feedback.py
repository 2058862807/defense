"""Regulatory feedback loop (real integration) tests.

Proves the pieces that make the loop real end-to-end: the regulatory API's
persistent ML-KEM keypair is stored encrypted at rest and reloadable, feedback
hybrid-encrypted to the served public key actually decrypts with the server's
secret key (with AAD), and the plaintext round-trips intact.
"""

import base64
import json

import pytest

from app.core.config import settings
from app.regulatory import keys
from app.regulatory.keys import (
    _LEGACY_KV_PATH,
    decrypt_regulatory_payload,
    load_or_create_regulatory_keypair,
    regulatory_public_key,
)


@pytest.fixture(autouse=True)
def _regulatory_store(tmp_path, monkeypatch):
    """Throwaway encrypted store + master key so the keypair never touches the
    real data/secrets.enc, and reset the module-level in-memory fallback."""
    monkeypatch.setattr(settings, "secrets_store_path", str(tmp_path / "secrets.enc"))
    monkeypatch.setenv("SECRETS_MASTER_KEY", "test-master-key-0123456789")
    monkeypatch.setattr(keys, "_in_memory", None)


def test_keypair_is_persisted_encrypted():
    pub1, _, variant = load_or_create_regulatory_keypair()
    assert pub1 and len(pub1) > 0
    assert variant == settings.ml_kem_variant
    # Same instance: second call must reload from the encrypted store, not
    # generate a fresh keypair (so client and server agree on the key).
    pub2, _, _ = load_or_create_regulatory_keypair()
    assert pub1 == pub2


def test_keypair_reloadable_from_fresh_module_state(tmp_path, monkeypatch):
    load_or_create_regulatory_keypair()
    # Simulate a new process sharing the same store path + master key.
    monkeypatch.setattr(keys, "_in_memory", None)
    pub1, _, _ = load_or_create_regulatory_keypair()
    from app.core.secrets_store import _load_store
    stored = _load_store().get(_LEGACY_KV_PATH)
    assert stored is not None
    assert base64.b64decode(stored["public_key"]) == pub1


def test_public_key_matches_stored_secret_key():
    pub, sec, _ = load_or_create_regulatory_keypair()
    from app.core.secrets_store import _load_store
    stored = _load_store().get(_LEGACY_KV_PATH)
    assert base64.b64decode(stored["public_key"]) == pub
    assert base64.b64decode(stored["secret_key"]) == sec
    assert regulatory_public_key() == pub


def test_hybrid_encryption_roundtrip_with_aad():
    payload = {"tx_hash": "0xabc", "risk_score": 0.9, "fairness": {"is_fair": True}}
    pub, _, variant = load_or_create_regulatory_keypair()

    from app.core.security import hybrid_encrypt_gov
    aad = json.dumps({"policy_version": settings.fairness_policy_version}).encode()
    enc = hybrid_encrypt_gov(pub, json.dumps(payload).encode(), associated_data=aad, variant=variant)

    assert enc["kem_alg"] == variant
    assert enc["dem_alg"] == "AES-256-GCM"
    assert enc["aad"]

    decrypted = decrypt_regulatory_payload(enc)
    assert decrypted == payload


def test_roundtrip_without_aad():
    payload = {"user_hash": "0xdeadbeef", "onchain_hash": "0x01"}
    pub, _, variant = load_or_create_regulatory_keypair()
    from app.core.security import hybrid_encrypt_gov
    enc = hybrid_encrypt_gov(pub, json.dumps(payload).encode(), variant=variant)
    assert enc["aad"] is None
    assert decrypt_regulatory_payload(enc) == payload


def test_decrypt_rejects_tampered_ciphertext():
    payload = {"tx_hash": "0xabc"}
    pub, _, variant = load_or_create_regulatory_keypair()
    from app.core.security import hybrid_encrypt_gov
    enc = hybrid_encrypt_gov(pub, json.dumps(payload).encode(), variant=variant)
    enc["ciphertext"] = base64.b64encode(base64.b64decode(enc["ciphertext"])[:32]).decode()
    assert decrypt_regulatory_payload(enc) is None
