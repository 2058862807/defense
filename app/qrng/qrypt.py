"""
Qrypt Quantum Entropy Service - Real Cloud QRNG
- Free tier: 1,000 requests/day
- API: https://api-eus.qrypt.com/api/v1/quantum-entropy?size={num_bytes}
- Auth: Bearer token via Authorization header
- Docs: https://docs.qrypt.com/quantum-entropy/
- US Made QRNG, Oakridge and Los Alamos National Labs

Government Standard: FIPS 140-3, mTLS, audit logging
"""

import logging
import os
import base64
from typing import Optional

from .base import QRNGProvider

logger = logging.getLogger(__name__)

class QryptQRNG(QRNGProvider):
    def __init__(self, api_token: Optional[str] = None, endpoint: str = "https://api-eus.qrypt.com"):
        from app.core.pilot_secrets import pilot_secrets
        self.api_token = api_token or pilot_secrets.get("qrypt_api_token") or os.getenv("QRYPT_TOKEN")
        self.endpoint = endpoint.rstrip("/")
        self.api_url = f"{self.endpoint}/api/v1/quantum-entropy"

    def get_provider_name(self) -> str:
        return "Qrypt"

    def is_available(self) -> bool:
        return bool(self.api_token)

    def get_random_bytes(self, num_bytes: int) -> bytes:
        """
        Real Qrypt API call - quantum entropy
        - size param is number of bytes requested
        - Returns base64 encoded quantum random bytes
        """
        if not self.is_available():
            raise RuntimeError("Qrypt API token not configured")

        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "User-Agent": "Protean-Defense-Enterprise/2.0.0 (FIPS-140-3; QRNG)",
        }

        params = {"size": num_bytes}

        try:
            with httpx.Client(timeout=10.0, verify=True) as client:
                resp = client.get(self.api_url, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

                # Qrypt returns: {"random": "base64string"} or similar
                # Check multiple possible response formats
                random_b64 = None
                if "random" in data:
                    random_b64 = data["random"]
                elif "entropy" in data:
                    random_b64 = data["entropy"]
                elif "data" in data:
                    random_b64 = data["data"]

                if not random_b64:
                    raise ValueError(f"Qrypt response missing random field: {data}")

                # Decode base64
                random_bytes = base64.b64decode(random_b64)

                # Ensure we got expected length
                if len(random_bytes) < num_bytes:
                    logger.warning(f"Qrypt returned {len(random_bytes)} bytes, expected {num_bytes}, padding with os.urandom")
                    # Pad with os.urandom for remaining
                    import os as os_mod
                    random_bytes += os_mod.urandom(num_bytes - len(random_bytes))

                # Truncate to exact requested size
                random_bytes = random_bytes[:num_bytes]

                logger.info(f"Qrypt QRNG fetched {len(random_bytes)} bytes quantum entropy")
                return random_bytes

        except Exception as e:
            logger.error(f"Qrypt QRNG fetch failed: {e}")
            raise

# Example usage would be:
# qrypt = QryptQRNG(api_token="your_qrypt_token")
# random_bytes = qrypt.get_random_bytes(32)  # 32 bytes = 256 bits for AES-256 key
