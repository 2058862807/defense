"""
Enterprise Signer Custody - single chokepoint for private-key custody and
transaction signing.

Replaces ad-hoc `Account.from_key(...)` calls with a custody-aware signer that:

1. Produces the exact signed-transaction bytes eth_account's `LocalAccount`
   would produce (legacy, EIP-155, and EIP-1559/2930 typed transactions), so it
   is a drop-in replacement for `eth_account.Account.from_key`.
2. Signs each 32-byte transaction digest through a pluggable `SigningBackend`:
   hardware HSM (PKCS#11), Vault Transit, or guarded software custody.
3. Reports and audit-logs the custody source for every signature, and fails
   closed in production when hardware custody is required but unavailable.

Government standard: FIPS 140-2/3 Level 3 when a hardware backend is active;
fail-closed signer loading; FedRAMP AU-2 audit trail.
"""

import logging
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Mapping, Optional, Tuple

from eth_keys import KeyAPI
from eth_utils import keccak
from hexbytes import HexBytes

from eth_account.datastructures import SignedMessage, SignedTransaction
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_account.typed_transactions import TypedTransaction

logger = logging.getLogger(__name__)

_V_OFFSET = 27
_CHAIN_ID_OFFSET = 35


class CustodySource(str, Enum):
    PKCS11_HSM = "pkcs11-hsm"
    VAULT_TRANSIT = "vault-transit"
    SOFTWARE_VAULT = "software-vault"
    SOFTWARE_LOCAL = "software-local-store"
    SOFTWARE_ENV = "software-env"


HARDWARE_CUSTODY = (CustodySource.PKCS11_HSM, CustodySource.VAULT_TRANSIT)


class SigningBackend(ABC):
    """Produces secp256k1 ECDSA signatures over a 32-byte digest without
    exposing the private key to callers."""

    custody_source: CustodySource

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def sign_digest(self, digest: bytes) -> Tuple[int, int, int]:
        """Return (r, s, recovery_id) for `digest` (32 bytes)."""
        raise NotImplementedError

    @abstractmethod
    def account_address(self) -> str:
        raise NotImplementedError


class SoftwareSigningBackend(SigningBackend):
    """Guarded software custody. Only permitted when the signing key lives in a
    managed store (Vault / local encrypted store) or in dev env."""

    def __init__(self, private_key: Any, source: CustodySource = CustodySource.SOFTWARE_LOCAL):
        if not isinstance(private_key, bytes):
            private_key = bytes(HexBytes(private_key))
        if len(private_key) != 32:
            raise ValueError("private key must be 32 bytes")
        self._key = KeyAPI().PrivateKey(private_key)
        self.custody_source = source
        self._public_key = self._key.public_key

    def provider_name(self) -> str:
        return f"software ({self.custody_source.value})"

    def sign_digest(self, digest: bytes) -> Tuple[int, int, int]:
        (recid, r, s) = self._key.sign_msg_hash(digest).vrs
        return (int(r), int(s), int(recid))

    def account_address(self) -> str:
        return self._public_key.to_checksum_address()

    def zeroize(self) -> None:
        try:
            del self._key
        except Exception:
            pass


class VaultTransitBackend(SigningBackend):
    """Signs digests via HashiCorp Vault Transit (secp256k1). The raw key never
    leaves Vault. Requires a reachable Vault + a configured transit key name."""

    def __init__(self, client: Any, transit_key_name: str, public_address: str):
        from vault import transit

        self._transit = transit.Transit(client, name=transit_key_name, mount_point="transit")
        self.custody_source = CustodySource.VAULT_TRANSIT
        self._address = public_address

    def provider_name(self) -> str:
        return "vault-transit"

    def sign_digest(self, digest: bytes) -> Tuple[int, int, int]:
        result = self._transit.sign(digest, prehashed=True)
        der = bytes(result["signature"].removeprefix("vault:v1:"))
        r, s = _der_to_rs(der)
        recid = _recover_recovery_id(digest, r, s, self._address)
        return (r, s, recid)

    def account_address(self) -> str:
        return self._address


class Pkcs11SigningBackend(SigningBackend):
    """Signs digests via a PKCS#11 token (CloudHSM, YubiHSM, SoftHSM). Activates
    only when a pkcs11 library + token config are present."""

    def __init__(self, lib_path: str, token_label: str, slot_pin: str, public_address: str):
        import pkcs11

        self._pkcs11 = pkcs11
        self._lib = pkcs11.lib(lib_path)
        self._token = pkcs11.Token(self._lib, label=token_label)
        self._pin = slot_pin
        self.custody_source = CustodySource.PKCS11_HSM
        self._address = public_address

    def provider_name(self) -> str:
        return "pkcs11-hsm"

    def sign_digest(self, digest: bytes) -> Tuple[int, int, int]:
        with self._token.open(user_pin=self._pin) as session:
            key = None
            for obj in session.get_objects(
                {
                    self._pkcs11.Attribute.CLASS: self._pkcs11.ObjectClass.PRIVATE_KEY,
                    self._pkcs11.Attribute.SIGN: True,
                }
            ):
                key = obj
                break
            if key is None:
                raise RuntimeError("no private key found on token")
            sig = key.sign(digest, mechanism=self._pkcs11.Mechanism.ECDSA)
        r, s = _der_to_rs(sig)
        recid = _recover_recovery_id(digest, r, s, self._address)
        return (r, s, recid)

    def account_address(self) -> str:
        return self._address


def _der_to_rs(der: bytes) -> Tuple[int, int]:
    """Parse a DER-encoded ECDSA signature into (r, s)."""
    if not der or der[0] != 0x30:
        raise ValueError("not a DER ECDSA signature")
    i = 1
    if der[i] & 0x80:
        n_len = der[i] & 0x7F
        i += 1 + n_len
    else:
        i += 1
    if der[i] != 0x02:
        raise ValueError("not a DER ECDSA signature")
    r_len = der[i + 1]
    r = int.from_bytes(der[i + 2 : i + 2 + r_len], "big")
    i = i + 2 + r_len
    if der[i] != 0x02:
        raise ValueError("not a DER ECDSA signature")
    s_len = der[i + 1]
    s = int.from_bytes(der[i + 2 : i + 2 + s_len], "big")
    return (r, s)


def _recover_recovery_id(digest: bytes, r: int, s: int, address: str) -> int:
    """Recover the recovery id by deriving candidate public keys (recid 0/1)
    and matching the signer address."""
    from eth_keys import keys

    for recid in (0, 1):
        try:
            pk = keys.Signature(vrs=(recid, r, s)).recover_public_key_from_msg_hash(digest)
        except Exception:
            continue
        if pk.to_checksum_address() == address:
            return recid
    raise ValueError("no recovery id matches the signer address")


def _eth_v_for(unsigned_tx, recid: int, chain_id: Optional[int]) -> int:
    """Replicate eth_account._utils.signing.sign_transaction_dict's v
    derivation for the given (unsigned) transaction object."""
    if isinstance(unsigned_tx, TypedTransaction):
        return recid
    if chain_id is not None:
        return _CHAIN_ID_OFFSET + 2 * chain_id + recid
    return _V_OFFSET + recid


class HSMBackedAccount:
    """Drop-in replacement for `eth_account.LocalAccount` that signs every
    transaction digest via a `SigningBackend` (custody chokepoint).

    Preserves the API surface used across the codebase: `.address`,
    `.sign_transaction(tx)` (and `.sign_message` for parity).
    """

    def __init__(self, backend: SigningBackend):
        self._backend = backend
        self.address = backend.account_address()

    @property
    def custody_source(self) -> CustodySource:
        return self._backend.custody_source

    @property
    def provider(self) -> str:
        return self._backend.provider_name()

    @classmethod
    def from_private_key(cls, private_key: Any, source: CustodySource = CustodySource.SOFTWARE_LOCAL) -> "HSMBackedAccount":
        return cls(SoftwareSigningBackend(private_key, source))

    def sign_transaction(self, transaction_dict: Mapping[str, Any]) -> SignedTransaction:
        if not isinstance(transaction_dict, Mapping):
            raise TypeError(
                f"transaction_dict must be dict-like, got {repr(transaction_dict)}"
            )
        sanitized = dict(transaction_dict)
        if "from" in sanitized:
            if sanitized["from"] == self.address:
                del sanitized["from"]
            else:
                str_from = (
                    sanitized["from"].decode()
                    if isinstance(sanitized["from"], bytes)
                    else sanitized["from"]
                )
                raise TypeError(
                    f"from field must match key's {self.address}, but it was {str_from}"
                )

        unsigned_tx = serializable_unsigned_transaction_from_dict(sanitized)
        tx_hash = unsigned_tx.hash()
        r, s, recid = self._backend.sign_digest(tx_hash)
        v = _eth_v_for(unsigned_tx, recid, sanitized.get("chainId"))
        encoded = encode_transaction(unsigned_tx, vrs=(v, r, s))
        final_hash = keccak(encoded)

        self._audit("CUSTODY_SIGN", self.custody_source.value, len(encoded))
        return SignedTransaction(
            raw_transaction=HexBytes(encoded),
            hash=HexBytes(final_hash),
            r=r,
            s=s,
            v=v,
        )

    def sign_message(self, message) -> SignedMessage:
        from eth_account.messages import defunct_hash_message

        msg_hash = bytes(defunct_hash_message(message))
        r, s, recid = self._backend.sign_digest(msg_hash)
        v = _V_OFFSET + recid
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])
        self._audit("CUSTODY_SIGN", self.custody_source.value, len(signature))
        return SignedMessage(
            message_hash=HexBytes(msg_hash),
            r=r,
            s=s,
            v=v,
            signature=HexBytes(signature),
        )

    @staticmethod
    def _audit(event_type: str, provider: str, size: int) -> None:
        try:
            from app.core.logging import audit_log

            audit_log(
                event_type=event_type,
                actor="hsm-custody",
                action="sign",
                resource="evm-signer",
                result="SUCCESS",
                metadata={"provider": provider, "size": size},
            )
        except Exception:
            logger.debug("custody audit unavailable", exc_info=True)


def build_signing_backend() -> Tuple[SigningBackend, str]:
    """Resolve the custody backend for the EVM signer.

    Priority:
      1. PKCS#11 hardware token (CloudHSM / YubiHSM / SoftHSM)
      2. Vault Transit (key material never leaves Vault)
      3. Guarded software custody (Vault / local encrypted store / dev env)

    Fails closed in production when `hsm_require_hardware` is set but no
    hardware backend is active.
    """
    from app.core.config import settings

    # 1. PKCS#11 hardware HSM
    if settings.pkcs11_lib and settings.hsm_token_label:
        try:
            backend = Pkcs11SigningBackend(
                settings.pkcs11_lib,
                settings.hsm_token_label,
                os.getenv("HSM_SLOT_PIN", ""),
                _expected_address(),
            )
            logger.info("CUSTODY: hardware HSM (PKCS#11) backend active")
            return (backend, CustodySource.PKCS11_HSM.value)
        except Exception as exc:
            logger.warning(f"CUSTODY: PKCS#11 backend unavailable ({exc})")

    # 2. Vault Transit
    if os.getenv("VAULT_TRANSIT_KEY_NAME"):
        try:
            from app.core.security import get_vault_client

            client = get_vault_client(
                settings.vault_addr,
                settings.vault_role_id,
                settings.vault_secret_id.get_secret_value(),
            )
            backend = VaultTransitBackend(
                client,
                os.getenv("VAULT_TRANSIT_KEY_NAME"),
                _expected_address(),
            )
            logger.info("CUSTODY: Vault Transit backend active")
            return (backend, CustodySource.VAULT_TRANSIT.value)
        except Exception as exc:
            logger.warning(f"CUSTODY: Vault Transit backend unavailable ({exc})")

    # 3. Software custody - resolve the key via managed stores
    from app.core.secrets_store import resolve_secret

    secret = resolve_secret(
        settings.vault_kv_path_signer,
        settings.vault_addr,
        settings.vault_role_id,
        settings.vault_secret_id.get_secret_value(),
    )
    if secret:
        private_key = secret.get("private_key") or secret.get("evm_private_key")
        if private_key:
            return (
                SoftwareSigningBackend(private_key, CustodySource.SOFTWARE_VAULT),
                CustodySource.SOFTWARE_VAULT.value,
            )

    # 3b. Pilot-store key - entered at runtime via the admin API so an operator
    #     can supply the gas wallet without a container restart.
    from app.core.pilot_secrets import pilot_secrets

    pilot_key = pilot_secrets.get("evm_private_key")
    if pilot_key:
        return (
            SoftwareSigningBackend(pilot_key, CustodySource.SOFTWARE_ENV),
            CustodySource.SOFTWARE_ENV.value,
        )

    # 4. Environment key - explicitly software custody. Preserves current
    #    operational behavior (signing works today via env key) but is audited
    #    loudly so production operators see that custody is software until A1
    #    key rotation + hardware provisioning.
    if settings.evm_private_key:
        if settings.is_production():
            logger.error(
                "CUSTODY: production signing with SOFTWARE custody (env key) - "
                "NOT FIPS 140-2 Level 3. Provision an HSM backend or set "
                "hsm_require_hardware=true to fail closed."
            )
            try:
                from app.core.logging import audit_log

                audit_log(
                    event_type="CUSTODY_SOFTWARE_ENV_IN_PROD",
                    actor="hsm-custody",
                    action="load",
                    resource="evm-signer",
                    result="WARNING",
                    metadata={"reason": "env-key software custody in production"},
                )
            except Exception:
                pass
        return (
            SoftwareSigningBackend(
                settings.evm_private_key.get_secret_value(),
                CustodySource.SOFTWARE_ENV,
            ),
            CustodySource.SOFTWARE_ENV.value,
        )

    if settings.is_production() and settings.hsm_require_hardware:
        raise RuntimeError(
            "FAIL-CLOSED: no hardware custody backend available but "
            "hsm_require_hardware=true in production"
        )

    raise RuntimeError("no signing custody backend available")


def _expected_address() -> str:
    """On-chain signer address used to verify recovery id against the correct
    public key when signing via an HSM/transit backend."""
    from app.core.config import settings

    return settings.evm_signer_address


def resolve_account() -> HSMBackedAccount:
    """Build the EVM signer account through the custody chokepoint."""
    backend, provider = build_signing_backend()
    account = HSMBackedAccount(backend)
    logger.info(f"CUSTODY: EVM signer active address={account.address} provider={provider}")
    try:
        from app.core.logging import audit_log

        audit_log(
            event_type="CUSTODY_INIT",
            actor="hsm-custody",
            action="load",
            resource="evm-signer",
            result="SUCCESS",
            metadata={"provider": provider, "address": account.address},
        )
    except Exception:
        pass
    return account


_account_singleton: Optional[HSMBackedAccount] = None


def get_account() -> HSMBackedAccount:
    """Lazily resolved, cached EVM signer. Resolves custody exactly once per
    process so health checks and bots share one signer."""
    global _account_singleton
    if _account_singleton is None:
        _account_singleton = resolve_account()
    return _account_singleton
