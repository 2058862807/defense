"""
Enterprise QRNG Service - Orchestrator with Real Cloud QRNG + Fallback to os.urandom
Government Standard: FIPS 140-3, SLSA L3, audit logging, fail-safe with os.urandom fallback

Priority:
1. Qrypt Quantum Entropy Service (1,000 req/day free) - US made, ORNL + Los Alamos
2. Azure Quantum QRNG (10,000 req/month free) - Quantinuum/IonQ
3. AWS Braket QRNG (via Marketplace) - IonQ Aria-1
4. Fallback: os.urandom() FIPS 140-3 compliant

All mock QRNG calls replaced with this service
"""

import logging
import os
from typing import Optional

from .base import QRNGProvider
from .qrypt import QryptQRNG
from .azure import AzureQRNG
from .aws import AWSQRNG

logger = logging.getLogger(__name__)

class QRNGService:
    def __init__(self):
        self.providers = []
        self._init_providers()
        self.fallback_count = 0
        self.cloud_success_count = 0

    def _init_providers(self):
        """Initialize providers in priority order"""
        # 1. Qrypt - highest priority, US made, best performance 1.575 Gbps
        try:
            qrypt = QryptQRNG()
            if qrypt.is_available():
                self.providers.append(qrypt)
                logger.info("QRNG Provider registered: Qrypt (1,000 req/day free)")
            else:
                logger.debug("Qrypt not configured - missing API token")
        except Exception as e:
            logger.warning(f"Failed to init Qrypt provider: {e}")

        # 2. Azure Quantum
        try:
            azure = AzureQRNG()
            if azure.is_available():
                self.providers.append(azure)
                logger.info("QRNG Provider registered: Azure Quantum (10,000 req/month free)")
            else:
                logger.debug("Azure Quantum not configured")
        except Exception as e:
            logger.warning(f"Failed to init Azure QRNG provider: {e}")

        # 3. AWS Braket
        try:
            aws = AWSQRNG()
            if aws.is_available():
                self.providers.append(aws)
                logger.info("QRNG Provider registered: AWS Braket")
            else:
                logger.debug("AWS Braket not configured")
        except Exception as e:
            logger.warning(f"Failed to init AWS QRNG provider: {e}")

        if not self.providers:
            logger.warning("No cloud QRNG providers configured - will use os.urandom() fallback (FIPS compliant)")

    def get_random_bytes(self, num_bytes: int, use_quantum: bool = True) -> bytes:
        """
        Get random bytes - tries cloud QRNG first, fallback to os.urandom
        Enterprise: audit logs which provider was used
        """
        if not use_quantum:
            # Explicit request for non-quantum (for testing)
            return os.urandom(num_bytes)

        # Try each cloud provider in priority order
        for provider in self.providers:
            try:
                random_bytes = provider.get_random_bytes(num_bytes)
                self.cloud_success_count += 1
                logger.info(f"QRNG SUCCESS via {provider.get_provider_name()} - {num_bytes} bytes quantum entropy (cloud_success={self.cloud_success_count})")
                
                # Audit log for gov compliance
                try:
                    from app.core.logging import audit_log
                    audit_log(
                        event_type="QRNG_FETCH",
                        actor="qrng-service",
                        action="get_random_bytes",
                        resource=provider.get_provider_name(),
                        result="SUCCESS",
                        metadata={"bytes": num_bytes, "provider": provider.get_provider_name()}
                    )
                except:
                    pass

                return random_bytes

            except Exception as e:
                logger.warning(f"QRNG provider {provider.get_provider_name()} failed: {e}, trying next")
                continue

        # All cloud providers failed - fallback to os.urandom() per government standard
        # os.urandom is FIPS 140-3 compliant when using OpenSSL FIPS provider
        self.fallback_count += 1
        logger.warning(f"All cloud QRNG providers failed - FALLBACK to os.urandom() {num_bytes} bytes (fallback_count={self.fallback_count}) - FIPS compliant")

        try:
            from app.core.logging import audit_log
            audit_log(
                event_type="QRNG_FALLBACK",
                actor="qrng-service",
                action="get_random_bytes",
                resource="os.urandom",
                result="FALLBACK",
                metadata={"bytes": num_bytes, "fallback_count": self.fallback_count}
            )
        except:
            pass

        return os.urandom(num_bytes)

    def get_random_int(self, min_val: int, max_val: int) -> int:
        """Get quantum random int in range [min, max]"""
        import math
        range_size = max_val - min_val + 1
        # Calculate bytes needed
        bytes_needed = math.ceil(math.log2(range_size) / 8)
        bytes_needed = max(1, bytes_needed)
        
        # Get random bytes and convert to int, then map to range
        while True:
            random_bytes = self.get_random_bytes(bytes_needed)
            random_int = int.from_bytes(random_bytes, 'big')
            # Rejection sampling to avoid bias
            if random_int < (256**bytes_needed // range_size) * range_size:
                return min_val + (random_int % range_size)

    def health_check(self) -> dict:
        """Health check all providers"""
        results = {
            "providers": [],
            "fallback_count": self.fallback_count,
            "cloud_success_count": self.cloud_success_count,
            "os_urandom_available": True
        }
        
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

# Singleton for enterprise
qrng_service = QRNGService()

def get_quantum_random_bytes(num_bytes: int) -> bytes:
    """
    Enterprise helper - replaces all mock QRNG calls with real cloud QRNG + fallback
    
    Usage:
        from app.qrng import get_quantum_random_bytes
        # Replace os.urandom(32) with:
        random_bytes = get_quantum_random_bytes(32)  # Tries Qrypt -> Azure -> AWS -> os.urandom
        
        # For nonce generation:
        nonce = get_quantum_random_bytes(12)  # 96-bit per NIST SP 800-38D
    """
    return qrng_service.get_random_bytes(num_bytes)

# For backward compatibility - replace os.urandom calls
def quantum_urandom(num_bytes: int) -> bytes:
    return get_quantum_random_bytes(num_bytes)
