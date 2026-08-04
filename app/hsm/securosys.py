"""
Securosys CloudHSM - Real Cloud HSM
- Free tier: 1,000 operations/month
- FIPS 140-2 Level 3, Common Criteria EAL4+
- Swiss made, for government
- Docs: https://www.securosys.com/

Government Standard: HSM as a Service via REST API
"""

import logging
import os
from typing import Optional

from .base import HSMProvider

logger = logging.getLogger(__name__)

class SecurosysHSM(HSMProvider):
    def __init__(self,
                 api_url: Optional[str] = None,
                 auth_token: Optional[str] = None,
                 key_label: Optional[str] = None):
        self.api_url = api_url or os.getenv("SECUROSYS_API_URL", "https://us.securosys.cloud/api/v1")
        from app.core.pilot_secrets import pilot_secrets
        self.auth_token = auth_token or pilot_secrets.get("securosys_auth_token") or os.getenv("SECUROSYS_AUTH_TOKEN")
        self.key_label = key_label or os.getenv("SECUROSYS_KEY_LABEL", "protean-hsm-key")

    def get_provider_name(self) -> str:
        return "Securosys CloudHSM"

    def is_available(self) -> bool:
        return bool(self.api_url and self.auth_token)

    def sign(self, key_id: str, data: bytes) -> bytes:
        """
        Real Securosys CloudHSM signing via REST API
        - API: POST /api/v1/sign with key label and data base64
        - Auth: Bearer token
        """
        import httpx
        import base64

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Protean-Defense-Enterprise/2.0.0 (FIPS-140-2-Level3)",
        }

        payload = {
            "keyLabel": key_id or self.key_label,
            "data": base64.b64encode(data).decode(),
            "algorithm": "ECDSA_SHA256"  # or RSA
        }

        try:
            with httpx.Client(timeout=10.0, verify=True) as client:
                resp = client.post(f"{self.api_url}/sign", headers=headers, json=payload)
                resp.raise_for_status()
                result = resp.json()
                signature_b64 = result.get("signature") or result.get("signedData")
                if not signature_b64:
                    raise ValueError(f"Securosys response missing signature: {result}")
                signature = base64.b64decode(signature_b64)
                logger.info(f"Securosys CloudHSM signed {len(data)} bytes via {key_id}")
                return signature
        except Exception as e:
            logger.error(f"Securosys CloudHSM signing failed: {e}")
            raise

    def get_public_key(self, key_id: str) -> bytes:
        import httpx
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        try:
            with httpx.Client(timeout=10.0, verify=True) as client:
                resp = client.get(f"{self.api_url}/keys/{key_id or self.key_label}/public", headers=headers)
                resp.raise_for_status()
                result = resp.json()
                pem = result.get("publicKey") or result.get("pem")
                return pem.encode() if isinstance(pem, str) else pem
        except Exception as e:
            logger.error(f"Securosys get_public_key failed: {e}")
            raise
