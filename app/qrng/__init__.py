"""
Enterprise QRNG Module - Real Cloud Quantum Random Number Generation
Government Standard: FIPS 140-3, SLSA L3, real QRNG via cloud services with fallback to os.urandom

Free Tier Integration:
- Qrypt Quantum Entropy Service: 1,000 req/day free
- Azure Quantum QRNG: 10,000 req/month free
- AWS Quantum (Braket) QRNG: via AWS Marketplace

Fallback: os.urandom() FIPS 140-3 compliant
"""

from .service import QRNGService, qrng_service, get_quantum_random_bytes

__all__ = ["QRNGService", "qrng_service", "get_quantum_random_bytes"]
