"""
Local encrypted secrets store (AES-256-GCM, FIPS 140-3 DEM) + resolution chain.

Enterprise secret resolution order:
  1. HashiCorp Vault (AppRole) - the production source of truth.
  2. Local encrypted store (this module) - AES-256-GCM file at rest, keyed by
     Vault KV path, so a single-node or air-gapped deployment gets the same
     secret-handling contract without the Vault SaaS dependency.
  3. (Dev only) environment variables handled by the caller - never in prod.

The file at rest is a JSON object encrypted with AES-256-GCM using a 32-byte
key derived (SHA-256) from SECRETS_MASTER_KEY. Format on disk:
    version:1|base64(nonce + ciphertext)
Decryption is authenticated: any tampering fails the GCM tag check.
"""
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_STORE_VERSION = 1


def _derive_key(master_key: str) -> bytes:
    if not master_key or len(master_key) < 16:
        raise ValueError("SECRETS_MASTER_KEY must be at least 16 characters")
    return hashlib.sha256(master_key.encode("utf-8")).digest()


class SecretsStore:
    def __init__(self, path: str = "data/secrets.enc", master_key: Optional[str] = None):
        self.path = path
        self._key = _derive_key(master_key) if master_key else None

    def set_key(self, master_key: str) -> None:
        self._key = _derive_key(master_key)

    def _require_key(self) -> bytes:
        if self._key is None:
            raise RuntimeError("Secrets master key not configured (set SECRETS_MASTER_KEY)")
        return self._key

    def _read_raw(self) -> Dict[str, Any]:
        if not Path(self.path).exists():
            return {"version": _STORE_VERSION, "secrets": {}}
        blob = Path(self.path).read_text().strip()
        if not blob:
            return {"version": _STORE_VERSION, "secrets": {}}
        if "|" not in blob:
            raise ValueError("Secrets store format error")
        _, payload_b64 = blob.split("|", 1)
        nonce_plus_ct = base64.b64decode(payload_b64)
        nonce, ciphertext = nonce_plus_ct[:12], nonce_plus_ct[12:]
        aesgcm = AESGCM(self._require_key())
        plaintext = aesgcm.decrypt(nonce, ciphertext, b"protean-secrets-v1")
        return json.loads(plaintext.decode("utf-8"))

    def _write_raw(self, store: Dict[str, Any]) -> None:
        nonce = os.urandom(12)
        plaintext = json.dumps(store, sort_keys=True).encode("utf-8")
        aesgcm = AESGCM(self._require_key())
        ciphertext = aesgcm.encrypt(nonce, plaintext, b"protean-secrets-v1")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.path).write_text(f"v{_STORE_VERSION}|" + base64.b64encode(nonce + ciphertext).decode())
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def get(self, kv_path: str) -> Optional[Dict[str, Any]]:
        try:
            store = self._read_raw()
        except Exception as e:
            logger.error(f"Secrets store read failed (wrong key or corrupted file): {e}")
            return None
        return store.get("secrets", {}).get(kv_path)

    def set(self, kv_path: str, secret: Dict[str, Any]) -> None:
        store = self._read_raw()
        store.setdefault("secrets", {})[kv_path] = secret
        self._write_raw(store)

    def touch(self) -> None:
        """Materialize an empty encrypted store file if it does not exist."""
        if not Path(self.path).exists():
            self._write_raw({"version": _STORE_VERSION, "secrets": {}})

    def list_paths(self) -> list:
        try:
            store = self._read_raw()
        except Exception:
            return []
        return list(store.get("secrets", {}).keys())

    def health(self) -> Dict[str, Any]:
        """Store readiness probe: is the file present and decryptable right now?"""
        has_file = Path(self.path).exists()
        if self._key is None:
            return {"ok": False, "has_file": has_file, "key_configured": False,
                    "reason": "SECRETS_MASTER_KEY not configured (set env or source data/.secrets_master_key)"}
        try:
            self._read_raw()
            return {"ok": True, "has_file": has_file, "key_configured": True, "reason": None}
        except Exception as e:
            return {"ok": False, "has_file": has_file, "key_configured": True,
                    "reason": f"Store not decryptable with configured key (stale file or wrong key): {e}"}


# Shared singleton - key configured via SECRETS_MASTER_KEY env when available.
def _load_store() -> SecretsStore:
    from app.core.config import settings
    master = None
    if settings.secrets_master_key is not None:
        master = settings.secrets_master_key.get_secret_value()
    else:
        master = os.getenv("SECRETS_MASTER_KEY")
    return SecretsStore(path=settings.secrets_store_path, master_key=master)


def resolve_secret(secret_path: str, vault_addr: str, role_id: str, secret_id: str) -> Optional[Dict[str, Any]]:
    """Vault first, then local encrypted store. Returns None if neither has it."""
    try:
        from app.core.security import get_secret_from_vault
        return get_secret_from_vault(vault_addr, role_id, secret_id, secret_path)
    except Exception as e:
        logger.warning(f"Vault unavailable for {secret_path}: {e}")
    try:
        return _load_store().get(secret_path)
    except Exception as e:
        logger.error(f"Local secrets store unavailable: {e}")
    return None


# Shared instance used by tests/CLI.
secrets_store = SecretsStore(path="data/secrets.enc")
