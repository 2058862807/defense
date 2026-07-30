"""
HSM Base - Abstract interface for Cloud HSM providers
Government Standard: FIPS 140-2 Level 3, audit logging
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class HSMProvider(ABC):
    @abstractmethod
    def sign(self, key_id: str, data: bytes) -> bytes:
        """Sign data with HSM key"""
        pass

    @abstractmethod
    def get_public_key(self, key_id: str) -> bytes:
        """Get public key for key_id"""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    def health_check(self) -> bool:
        try:
            if not self.is_available():
                return False
            # Try to list keys or sign 1 byte
            self.get_public_key("test") if hasattr(self, 'get_public_key') else None
            return True
        except Exception as e:
            logger.warning(f"HSM health check failed for {self.get_provider_name()}: {e}")
            return False
