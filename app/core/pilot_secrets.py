"""
Pilot credential store - enter third-party API credentials at runtime.

A pilot / operator can supply real credentials (Chainalysis, TRM, Qrypt,
Azure, AWS, CloudHSM, Securosys, Flashbots, EVM signer) once via the
/pilot/credentials admin API. They are persisted in the existing encrypted
secrets store (data/secrets.enc, AES-256-GCM under SECRETS_MASTER_KEY) and
resolved at call time so no restart is required.

Resolution order per field: environment variable (highest) -> encrypted store.

Never logs or echoes the value back; status endpoints return configured: bool
and source only.
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# field -> (env var, human label)
PILOT_CREDENTIALS: Dict[str, tuple] = {
    "chainalysis_api_token": ("CHAINALYSIS_API_TOKEN", "Chainalysis Sanctions API token (api.chainalysis.com)"),
    "trm_api_token": ("TRM_API_TOKEN", "TRM Labs Screen API token (api.trmlabs.com)"),
    "qrypt_api_token": ("QRYPT_API_TOKEN", "Qrypt Quantum Entropy token (api-eus.qrypt.com)"),
    "qrypt_aws_marketplace_token": ("QRYPT_AWS_MARKETPLACE_TOKEN", "Qrypt Entropy-as-a-Service (AWS Marketplace) token"),
    "azure_quantum_connection_string": ("AZURE_QUANTUM_CONNECTION_STRING", "Azure Quantum connection string"),
    "aws_access_key_id": ("AWS_ACCESS_KEY_ID", "AWS access key id (Braket / CloudHSM)"),
    "aws_secret_access_key": ("AWS_SECRET_ACCESS_KEY", "AWS secret access key"),
    "aws_cloudhsm_password": ("AWS_CLOUDHSM_PASSWORD", "AWS CloudHSM CU password"),
    "securosys_auth_token": ("SECUROSYS_AUTH_TOKEN", "Securosys CloudHSM auth token"),
    "evm_private_key": ("EVM_PRIVATE_KEY", "Gas wallet private key (0x-prefixed) for tx signing"),
    "flashbots_signing_key": ("FLASHBOTS_SIGNING_KEY", "Flashbots relay auth signer private key (0x-prefixed)"),
}

_STORE_PATH = "pilot/credentials"


def _load_store():
    from app.core.secrets_store import _load_store as _build_secrets_store
    return _build_secrets_store()


class PilotSecretsStore:
    """Flat credential map persisted in the encrypted secrets store."""

    def __init__(self, store=None, path: str = _STORE_PATH):
        self.store = store if store is not None else _load_store()
        self.path = path

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #
    def _dict(self) -> Dict[str, Any]:
        try:
            return dict(self.store.get(self.path) or {})
        except Exception as e:
            logger.error(f"Pilot secrets store read failed: {e}")
            return {}

    def get(self, field: str) -> Optional[str]:
        """Resolve a credential: env var wins, then the encrypted store."""
        if field not in PILOT_CREDENTIALS:
            return None
        env_var = PILOT_CREDENTIALS[field][0]
        env_val = os.getenv(env_var)
        if env_val:
            return env_val
        return self._dict().get(field)

    def set(self, field: str, value: str) -> Dict[str, Any]:
        """Persist a credential. Raises KeyError for unknown fields."""
        if field not in PILOT_CREDENTIALS:
            raise KeyError(f"Unknown pilot credential field: {field}")
        if not value or not isinstance(value, str):
            raise ValueError("Credential value must be a non-empty string")
        data = self._dict()
        data[field] = value
        self.store.set(self.path, data)
        logger.info(f"Pilot credential stored: {field} (source=store)")
        return self.status(field)

    def delete(self, field: str) -> bool:
        """Remove a credential from the store (env vars still win if set)."""
        if field not in PILOT_CREDENTIALS:
            raise KeyError(f"Unknown pilot credential field: {field}")
        data = self._dict()
        if field not in data:
            return False
        del data[field]
        self.store.set(self.path, data)
        logger.info(f"Pilot credential removed: {field}")
        return True

    def status(self, field: str) -> Dict[str, Any]:
        if field not in PILOT_CREDENTIALS:
            raise KeyError(f"Unknown pilot credential field: {field}")
        env_var, label = PILOT_CREDENTIALS[field]
        in_env = bool(os.getenv(env_var))
        in_store = field in self._dict()
        source = "env" if in_env else ("store" if in_store else "none")
        return {"field": field, "env_var": env_var, "label": label,
                "configured": in_env or in_store, "source": source}

    def snapshot(self) -> List[Dict[str, Any]]:
        return [self.status(f) for f in PILOT_CREDENTIALS]

    def refresh(self) -> None:
        """Re-init runtime integrations that cache credentials at construction."""
        try:
            from app.qrng.service import qrng_service
            qrng_service.refresh()
        except Exception as e:
            logger.warning(f"QRNG refresh failed: {e}")
        try:
            from app.hsm.service import hsm_service
            hsm_service.refresh()
        except Exception as e:
            logger.warning(f"HSM refresh failed: {e}")
        logger.info("Pilot credential refresh triggered (QRNG/HSM re-initialized)")


# Shared singleton (lazy store: key from SECRETS_MASTER_KEY).
pilot_secrets = PilotSecretsStore()
