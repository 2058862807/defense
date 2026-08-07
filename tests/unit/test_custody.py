"""Signature-parity tests for HSMBackedAccount vs eth_account.LocalAccount.

Critical property: the custody-backed signer must produce byte-identical
signed transactions (legacy, EIP-155, and EIP-1559/2930) to the reference
`Account.from_key(...)` implementation, so it is a safe drop-in replacement.
"""

import pytest

from eth_account import Account
from eth_account.messages import encode_defunct

from app.hsm.custody import (
    CustodySource,
    HSMBackedAccount,
    SoftwareSigningBackend,
    build_signing_backend,
    _der_to_rs,
)

KEY = "0x" + "01" * 32
TO = "0x" + "22" * 20


def _txs():
    base = {"nonce": 0, "gas": 21000, "to": TO, "value": 1, "data": b""}
    return {
        "legacy_no_chain": dict(base, gasPrice=10),
        "eip155": dict(base, gasPrice=10, chainId=137),
        "eip1559": dict(base, type=2, maxFeePerGas=10, maxPriorityFeePerGas=1, chainId=137),
        "eip2930": dict(
            base,
            type=1,
            gasPrice=10,
            chainId=137,
            accessList=[{"address": TO, "storageKeys": []}],
        ),
    }


@pytest.mark.parametrize("name", ["legacy_no_chain", "eip155", "eip1559", "eip2930"])
def test_sign_transaction_byte_parity(name):
    tx = _txs()[name]
    reference = Account.from_key(KEY)
    custody = HSMBackedAccount.from_private_key(KEY)

    ref_signed = reference.sign_transaction(tx)
    cus_signed = custody.sign_transaction(tx)

    assert custody.address == reference.address
    assert cus_signed.raw_transaction == ref_signed.raw_transaction
    assert cus_signed.hash == ref_signed.hash
    assert cus_signed.v == ref_signed.v
    assert cus_signed.r == ref_signed.r
    assert cus_signed.s == ref_signed.s


def test_from_field_must_match():
    custody = HSMBackedAccount.from_private_key(KEY)
    tx = dict(_txs()["eip1559"])
    tx["from"] = custody.address
    ref = Account.from_key(KEY).sign_transaction(tx)
    assert custody.sign_transaction(tx).raw_transaction == ref.raw_transaction

    bad = dict(tx)
    bad["from"] = "0x" + "33" * 20
    with pytest.raises(TypeError):
        custody.sign_transaction(bad)


def test_sign_message_parity():
    custody = HSMBackedAccount.from_private_key(KEY)
    ref = Account.from_key(KEY)
    msg = b"hello protean defense"

    cus = custody.sign_message(msg)
    ref_msg = ref.sign_message(encode_defunct(msg))

    assert cus.signature == ref_msg.signature
    assert cus.message_hash == ref_msg.message_hash


def test_custody_source_reporting():
    account = HSMBackedAccount.from_private_key(KEY, CustodySource.SOFTWARE_VAULT)
    assert account.custody_source == CustodySource.SOFTWARE_VAULT
    assert "software" in account.provider


def test_der_to_rs_roundtrip():
    from ecdsa import SECP256k1, SigningKey
    from ecdsa.util import sigencode_der

    digest = b"\x42" * 32
    sk = SigningKey.from_string(bytes.fromhex("01" * 32), curve=SECP256k1)
    der = sk.sign_digest(digest, sigencode=sigencode_der)
    r, s = _der_to_rs(der)
    assert r > 0 and s > 0
    assert r < SECP256k1.order and s < SECP256k1.order


def test_build_signing_backend_dev_env(monkeypatch):
    # hsm_require_hardware now defaults to True, so software/env-key custody
    # (what this repo's .env is configured with) must be explicitly opted
    # into for local/dev testing rather than being silently permitted.
    from app.core.config import settings

    monkeypatch.setattr(settings, "hsm_require_hardware", False)
    backend, provider = build_signing_backend()
    assert backend.account_address()
    assert provider in {s.value for s in CustodySource}


def test_build_signing_backend_fails_closed_without_hardware(monkeypatch):
    """hsm_require_hardware=true in production must refuse to sign with
    software/env-key custody, even if a key happens to be configured."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "hsm_require_hardware", True)
    monkeypatch.setattr(settings, "env", "production")
    with pytest.raises(RuntimeError, match="hsm_require_hardware=true"):
        build_signing_backend()
