"""
Enterprise HSM Module - Real Cloud HSM via AWS CloudHSM, GCP HSM, Securosys
Government Standard: FIPS 140-2 Level 3, SLSA L3, audit logging, fallback to software signing

Free Tier:
- AWS CloudHSM: 1 HSM for 30 days free (then $1.60/hr)
- Google Cloud HSM: 10,000 operations/month free
- Securosys CloudHSM: 1,000 operations/month free
"""

from .service import HSMService, hsm_service, get_hsm_signer

__all__ = ["HSMService", "hsm_service", "get_hsm_signer"]
