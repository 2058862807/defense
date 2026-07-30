"""
Google Cloud HSM - Real Cloud HSM
- Free tier: 10,000 operations/month
- FIPS 140-2 Level 3
- Docs: https://cloud.google.com/kms/docs/hsm

Government Standard: GCP IAM, audit logging
"""

import logging
import os
from typing import Optional

from .base import HSMProvider

logger = logging.getLogger(__name__)

class GCPCloudHSM(HSMProvider):
    def __init__(self,
                 project_id: Optional[str] = None,
                 location: Optional[str] = None,
                 key_ring: Optional[str] = None,
                 key_id: Optional[str] = None):
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self.location = location or os.getenv("GCP_KMS_LOCATION", "us-east1")
        self.key_ring = key_ring or os.getenv("GCP_KMS_KEY_RING", "protean-ring")
        self.key_id = key_id or os.getenv("GCP_KMS_KEY_ID", "protean-hsm-key")

    def get_provider_name(self) -> str:
        return "GCP Cloud HSM"

    def is_available(self) -> bool:
        return bool(self.project_id and self.key_ring)

    def sign(self, key_id: str, data: bytes) -> bytes:
        """
        Real GCP Cloud HSM signing via Cloud KMS API with HSM protection level
        """
        try:
            from google.cloud import kms
            import hashlib

            client = kms.KeyManagementServiceClient()

            # Build key version name
            # Format: projects/*/locations/*/keyRings/*/cryptoKeys/*/cryptoKeyVersions/*
            # For simplicity, use latest version
            key_name = client.crypto_key_path(
                project=self.project_id,
                location=self.location,
                key_ring=self.key_ring,
                crypto_key=key_id or self.key_id
            )

            # Hash data per GCP KMS requirement (SHA256)
            digest = {"sha256": hashlib.sha256(data).digest()}

            # Sign via Cloud HSM - key must have protection_level HSM and purpose ASYMMETRIC_SIGN
            response = client.asymmetric_sign(
                request={"name": key_name, "digest": digest}
            )

            signature = response.signature
            logger.info(f"GCP Cloud HSM signed {len(data)} bytes via {key_id} - sig len {len(signature)}")
            return signature

        except ImportError:
            raise RuntimeError("google-cloud-kms not installed - required for GCP Cloud HSM")
        except Exception as e:
            logger.error(f"GCP Cloud HSM signing failed: {e}")
            raise

    def get_public_key(self, key_id: str) -> bytes:
        try:
            from google.cloud import kms
            client = kms.KeyManagementServiceClient()
            key_name = client.crypto_key_path(
                project=self.project_id,
                location=self.location,
                key_ring=self.key_ring,
                crypto_key=key_id or self.key_id
            )
            response = client.get_public_key(request={"name": key_name})
            return response.pem.encode() if hasattr(response, 'pem') else response.pem_bytes
        except Exception as e:
            logger.error(f"GCP get_public_key failed: {e}")
            raise
