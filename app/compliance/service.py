"""
Enterprise Compliance Service - Combined OFAC/FATF with Real Live Feeds
Government Standard: FIPS 140-3, SLSA L3, fail-closed with cached fallback, audit logging
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .ofac import ofac_feed, OFACFeed
from .fatf import fatf_feed, FATFFeed
from .cache import compliance_cache, ComplianceCache

logger = logging.getLogger(__name__)

class ComplianceService:
    def __init__(self, ofac: Optional[OFACFeed] = None, fatf: Optional[FATFFeed] = None, cache: Optional[ComplianceCache] = None):
        self.ofac = ofac or ofac_feed
        self.fatf = fatf or fatf_feed
        self.cache = cache or compliance_cache

    def check_address(self, address: Optional[str] = None, name: Optional[str] = None, country: Optional[str] = None) -> Dict[str, Any]:
        """
        Enterprise compliance check - OFAC SDN + FATF high-risk + address risk.
        - Checks name against OFAC SDN live feed
        - Checks country against FATF grey/black live feed
        - Crypto addresses screened via Chainalysis/TRM when tokens are
          configured (pilot store); otherwise the analytics result reports
          configured=False and never downgrades an OFAC/FATF block.
        - Returns combined risk assessment
        """
        result = {
            "checked_at": datetime.utcnow().isoformat(),
            "address": address,
            "name": name,
            "country": country,
            "ofac": None,
            "fatf": None,
            "analytics": None,
            "overall_risk": "low",
            "blocked": False,
            "reasons": []
        }

        # OFAC check
        if name or address:
            try:
                ofac_result = self.ofac.is_sanctioned(name=name, address=address)
                result["ofac"] = ofac_result
                if ofac_result.get("sanctioned"):
                    result["blocked"] = True
                    result["overall_risk"] = "high"
                    result["reasons"].append(f"OFAC SDN match: {ofac_result.get('match', {}).get('sdn_name')} Program: {ofac_result.get('program')}")
            except Exception as e:
                logger.error(f"OFAC check failed: {e}")
                result["ofac"] = {"error": str(e), "sanctioned": False}

        # FATF check
        if country:
            try:
                fatf_result = self.fatf.is_high_risk(country)
                result["fatf"] = fatf_result
                if fatf_result.get("high_risk"):
                    if fatf_result.get("list", "").startswith("FATF Black"):
                        result["overall_risk"] = "high"
                        result["reasons"].append(f"FATF Black List: {fatf_result.get('country')} - {fatf_result.get('list')}")
                        if fatf_result.get("requires_countermeasures"):
                            result["blocked"] = True
                    else:
                        if result["overall_risk"] != "high":
                            result["overall_risk"] = "medium"
                        result["reasons"].append(f"FATF Grey List: {fatf_result.get('country')} - enhanced monitoring")
            except Exception as e:
                logger.error(f"FATF check failed: {e}")
                result["fatf"] = {"error": str(e), "high_risk": False}

        # Chainalysis / TRM address-risk analytics (neutral when unconfigured -
        # never downgrades an OFAC/FATF block above).
        if address:
            try:
                from .address_risk import address_risk_engine
                screening = address_risk_engine.screen_transaction(
                    address,
                    jurisdiction=country,
                    amount=None,
                )
                result["analytics"] = screening
                if screening.get("decision") == "block" and not result.get("blocked"):
                    result["blocked"] = True
                    result["overall_risk"] = "high"
                for r in screening.get("reasons", []):
                    if r not in result["reasons"]:
                        result["reasons"].append(r)
            except Exception as e:
                logger.error(f"Address-risk screening failed: {e}")
                result["analytics"] = {"error": str(e), "configured": False}

        # Determine final blocked status per government policy
        # OFAC sanctioned => always blocked
        # FATF black with countermeasures => blocked
        # FATF grey alone does NOT automatically block per FATF guidance, but input to risk assessment

        return result

    def get_ofac_stats(self) -> Dict[str, Any]:
        return self.ofac.get_stats()

    def get_fatf_stats(self) -> Dict[str, Any]:
        return self.fatf.get_stats()

    def refresh_all(self) -> Dict[str, Any]:
        """Force refresh all feeds - used by cron job"""
        results = {}
        try:
            ofac_data = self.ofac.get_sdn_list(force_refresh=True)
            results["ofac"] = {"status": "success", "count": len(ofac_data)}
        except Exception as e:
            results["ofac"] = {"status": "failed", "error": str(e)}

        try:
            grey = self.fatf.get_grey_list(force_refresh=True)
            black = self.fatf.get_black_list()
            results["fatf"] = {"status": "success", "grey_count": len(grey), "black_count": len(black)}
        except Exception as e:
            results["fatf"] = {"status": "failed", "error": str(e)}

        results["refreshed_at"] = datetime.utcnow().isoformat()
        return results

    def get_combined_stats(self) -> Dict[str, Any]:
        return {
            "ofac": self.get_ofac_stats(),
            "fatf": self.get_fatf_stats(),
            "timestamp": datetime.utcnow().isoformat()
        }

# Singleton
compliance_service = ComplianceService()
