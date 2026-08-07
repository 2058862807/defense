"""
Regulatory PQC keypair (real integration).

The regulatory API owns a persistent ML-KEM (FIPS 203) keypair. Its public key
is served over `GET /regulatory/pqc/pubkey` (mTLS + JWT) so the defense bot can
hybrid-encrypt feedback to a key the server can actually decrypt. The keypair
is persisted in the encrypted SecretsStore (AES-256-GCM at rest) keyed by the
same Vault KV path contract as other secrets, so single-node and distributed
deployments behave identically.

Fail-closed: without a usable store the pubkey endpoint refuses (no ephemeral
keys that would make encryption undecryptable). A non-prod in-memory fallback
exists only for local testing where SECRETS_MASTER_KEY is absent.
"""
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

_LEGACY_KV_PATH = "secret/data/prod/regulatory-pqc-keypair"
_in_memory: Optional[Dict[str, str]] = None


def _store() -> "object":
    from app.core.secrets_store import _load_store
    return _load_store()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def load_or_create_regulatory_keypair() -> Optional[Tuple[bytes, bytes, str]]:
    """Return (public_key, secret_key, variant) or None when the store is unusable."""
    global _in_memory
    try:
        store = _store()
        existing = store.get(_LEGACY_KV_PATH)
        if existing and existing.get("public_key") and existing.get("secret_key"):
            return (
                base64.b64decode(existing["public_key"]),
                base64.b64decode(existing["secret_key"]),
                existing.get("variant", settings.ml_kem_variant),
            )
    except Exception as e:
        logger.warning(f"Regulatory keypair store unavailable: {e}")
        if settings.is_production():
            return None

    # Non-prod only: ephemeral in-memory keypair so the loop works without a
    # master key. Never persisted; production fails closed above.
    if _in_memory:
        return (
            base64.b64decode(_in_memory["public_key"]),
            base64.b64decode(_in_memory["secret_key"]),
            _in_memory["variant"],
        )
    try:
        from app.core.security import ml_kem_keypair
        pub, sec = ml_kem_keypair(settings.ml_kem_variant)
    except Exception as e:
        logger.error(f"Regulatory keypair generation failed: {e}")
        return None

    try:
        entry = {
            "public_key": _b64(pub),
            "secret_key": _b64(sec),
            "variant": settings.ml_kem_variant,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _store().set(_LEGACY_KV_PATH, entry)
        logger.info("Regulatory PQC keypair persisted in encrypted store")
    except Exception as e:
        logger.warning(f"Could not persist regulatory keypair: {e}")
        if settings.is_production():
            return None
        _in_memory = {
            "public_key": _b64(pub),
            "secret_key": _b64(sec),
            "variant": settings.ml_kem_variant,
        }

    return pub, sec, settings.ml_kem_variant


def regulatory_public_key() -> Optional[bytes]:
    pair = load_or_create_regulatory_keypair()
    return pair[0] if pair else None


def decrypt_regulatory_payload(enc: Dict[str, str]) -> Optional[dict]:
    """Decrypt a hybrid-encrypted feedback payload with the server's key."""
    from app.core.security import hybrid_decrypt_gov

    pair = load_or_create_regulatory_keypair()
    if not pair:
        logger.error("Regulatory PQC private key unavailable - cannot decrypt feedback")
        return None
    pub, sec, variant = pair
    aad = base64.b64decode(enc["aad"]) if enc.get("aad") else None
    try:
        plaintext = hybrid_decrypt_gov(
            enc["kem_ct"],
            enc["nonce"],
            enc["ciphertext"],
            secret_key=sec,
            associated_data=aad,
            variant=variant,
        )
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        logger.error(f"Regulatory payload decryption failed: {e}")
        return None
