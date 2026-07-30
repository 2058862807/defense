"""
QRNG Base - Abstract interface for cloud QRNG services
Government Standard: FIPS 140-3, audit logging, fail-closed with fallback
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class QRNGProvider(ABC):
    """Abstract base for QRNG cloud providers"""

    @abstractmethod
    def get_random_bytes(self, num_bytes: int) -> bytes:
        """Get quantum random bytes - must be overridden"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name for audit logging"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available"""
        pass

    def health_check(self) -> bool:
        """Health check - try to get 1 byte"""
        try:
            if not self.is_available():
                return False
            self.get_random_bytes(1)
            return True
        except Exception as e:
            logger.warning(f"QRNG health check failed for {self.get_provider_name()}: {e}")
            return False
