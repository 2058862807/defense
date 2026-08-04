"""
Enterprise HSM Service - Orchestrator with Real Cloud HSM + Fallback to Software Signing
Government Standard: FIPS 140-2 Level 3, SLSA L3, audit logging, fail-safe with software fallback

Priority:
1. AWS CloudHSM (1 HSM for 30 days free) - FIPS 140-2 Level 3, dedicated single-tenant
2. Google Cloud HSM (10,000 ops/month free) - FIPS 140-2 Level 3
3. Securosys CloudHSM (1,000 ops/month free) - FIPS 140-2 Level 3, Swiss

Fallback: Software signing via eth_account (for dev) or Vault Transit (for prod without HSM)
"""

import logging
from typing import Optional

from .base import HSMProvider
from .aws_cloudhsm import AWSCloudHSM
from .gcp_hsm import GCPCloudHSM
from .securosys import SecurosysHSM

logger = logging.getLogger(__name__)

class HSMSoftwareFallback:
    """Software custody fallback - resolves the real signing key through the
    custody chokepoint (Vault -> local encrypted store -> dev env) and signs
    with it. NEVER fabricates signatures."""

    def get_provider_name(self) -> str:
        return "Software Custody (managed store)"

    def is_available(self) -> bool:
        return True

    def _resolve_key(self, key_id: str) -> bytes:
        """Resolve the private key through the custody chokepoint. Fail closed:
        raise if no key is available - never sign with a fabricated key."""
        from app.core.config import settings
        from app.core.secrets_store import resolve_secret

        secret = resolve_secret(
            key_id,
            settings.vault_addr,
            settings.vault_role_id,
            settings.vault_secret_id.get_secret_value(),
        )
        if secret:
            priv_key = secret.get("private_key") or secret.get("evm_private_key")
            if priv_key:
                if not priv_key.startswith("0x"):
                    priv_key = "0x" + priv_key
                return bytes.fromhex(priv_key.removeprefix("0x"))

        if settings.env != "production" and settings.evm_private_key:
            return bytes.fromhex(settings.evm_private_key.get_secret_value().removeprefix("0x"))

        raise RuntimeError(
            "FAIL-CLOSED: software custody fallback has no signing key available"
        )

    def sign(self, key_id: str, data: bytes) -> bytes:
        """Sign `data` as an Ethereum signed message using the resolved key.
        Returns a real 65-byte secp256k1 signature."""
        from eth_account.messages import encode_defunct
        from eth_keys.datatypes import Signature

        from app.hsm.custody import SoftwareSigningBackend

        priv_key = self._resolve_key(key_id)
        backend = SoftwareSigningBackend(priv_key)
        msg_hash = bytes(encode_defunct(data).hash)
        r, s, recid = backend.sign_digest(msg_hash)
        signature = Signature(vrs=(27 + recid, r, s)).to_bytes()
        backend.zeroize()

        logger.warning(f"HSM FALLBACK to software custody via {key_id} - not FIPS 140-2 Level 3")
        return signature

    def get_public_key(self, key_id: str) -> bytes:
        return b"software-custody-public-key"

class HSMService:
    def __init__(self):
        self.providers = []
        self._init_providers()
        self.software_fallback = HSMSoftwareFallback()
        self.fallback_count = 0
        self.cloud_success_count = 0

    def _init_providers(self):
        # 1. AWS CloudHSM - highest priority, dedicated single-tenant
        try:
            aws = AWSCloudHSM()
            if aws.is_available():
                self.providers.append(aws)
                logger.info("HSM Provider registered: AWS CloudHSM (1 HSM 30 days free, FIPS 140-2 Level 3)")
        except Exception as e:
            logger.warning(f"Failed to init AWS CloudHSM: {e}")

        # 2. GCP Cloud HSM
        try:
            gcp = GCPCloudHSM()
            if gcp.is_available():
                self.providers.append(gcp)
                logger.info("HSM Provider registered: GCP Cloud HSM (10k ops/month free, FIPS 140-2 Level 3)")
        except Exception as e:
            logger.warning(f"Failed to init GCP Cloud HSM: {e}")

        # 3. Securosys CloudHSM
        try:
            securosys = SecurosysHSM()
            if securosys.is_available():
                self.providers.append(securosys)
                logger.info("HSM Provider registered: Securosys CloudHSM (1k ops/month free, Swiss)")
        except Exception as e:
            logger.warning(f"Failed to init Securosys HSM: {e}")

        if not self.providers:
            logger.warning("No cloud HSM providers configured - will use software fallback (Vault Transit or eth_account)")

    def refresh(self):
        """Re-initialize providers from current credentials (pilot store / env).

        Called after a credential change so newly entered tokens apply without
        a restart. Fail-open: a provider init error only drops that provider.
        """
        self.providers = []
        self._init_providers()

    def sign(self, key_id: str, data: bytes, use_hsm: bool = True) -> bytes:
        """Sign data - tries cloud HSM first, fallback to software"""
        if not use_hsm:
            return self.software_fallback.sign(key_id, data)

        for provider in self.providers:
            try:
                signature = provider.sign(key_id, data)
                self.cloud_success_count += 1
                logger.info(f"HSM SUCCESS via {provider.get_provider_name()} - {len(data)} bytes signed (cloud_success={self.cloud_success_count})")

                try:
                    from app.core.logging import audit_log
                    audit_log(
                        event_type="HSM_SIGN",
                        actor="hsm-service",
                        action="sign",
                        resource=provider.get_provider_name(),
                        result="SUCCESS",
                        metadata={"key_id": key_id, "data_len": len(data), "provider": provider.get_provider_name()}
                    )
                except:
                    pass

                return signature
            except Exception as e:
                logger.warning(f"HSM provider {provider.get_provider_name()} failed: {e}, trying next")
                continue

        # Fallback
        self.fallback_count += 1
        logger.warning(f"All cloud HSM providers failed - FALLBACK to software signing {len(data)} bytes (fallback_count={self.fallback_count})")

        try:
            from app.core.logging import audit_log
            audit_log(
                event_type="HSM_FALLBACK",
                actor="hsm-service",
                action="sign",
                resource="software",
                result="FALLBACK",
                metadata={"key_id": key_id, "fallback_count": self.fallback_count}
            )
        except:
            pass

        return self.software_fallback.sign(key_id, data)

    def health_check(self) -> dict:
        results = {"providers": [], "fallback_count": self.fallback_count, "cloud_success_count": self.cloud_success_count}
        for provider in self.providers:
            try:
                healthy = provider.health_check()
                results["providers"].append({
                    "name": provider.get_provider_name(),
                    "available": provider.is_available(),
                    "healthy": healthy
                })
            except Exception as e:
                results["providers"].append({
                    "name": provider.get_provider_name(),
                    "available": False,
                    "healthy": False,
                    "error": str(e)
                })
        return results

# Singleton
hsm_service = HSMService()

def get_hsm_signer():
    return hsm_service
