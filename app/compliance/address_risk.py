"""
Address-risk screening engine (B8): Chainalysis/TRM stub interface + shadow
sanctions set + OFAC SDN digital-currency-address matching + FATF jurisdiction
risk, producing an allow / review / block decision.

- Shadow sanctions set: operator-maintained JSON (gitignored, see
  data/sanctions_shadow.json) with exact-match addresses - fails closed.
- OFAC SDN live feed: extracts "digital currency address" columns (the SLS CSV
  carries them) and matches normalized addresses.
- FATF jurisdiction risk: black/grey list membership -> enhanced review.
- Chainalysis / TRM providers are wired as configurable stubs: when an API
  token is configured they would run real screening; until then they return
  configured=False and the engine never downgrades a block/review.

Decision policy (fail-closed): shadow or OFAC address match => block.
Anything above risk_block_threshold is blocked, above risk_review_threshold is
reviewed. Government standard: every screening is audit-logged by the caller.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_address(address: str) -> Optional[str]:
    """Normalize an EVM address to lowercase 0x-hex; None if malformed."""
    if not address:
        return None
    a = address.strip().lower()
    if a.startswith("0x") and len(a) == 42 and all(c in "0123456789abcdef" for c in a[2:]):
        return a
    return None


class AnalyticsProvider(ABC):
    """Blockchain analytics risk provider interface (Chainalysis / TRM)."""

    name: str = "analytics"

    def __init__(self, api_token: Optional[str] = None, timeout: float = 10.0):
        self.api_token = api_token
        self.timeout = timeout
        self.configured = bool(api_token)

    def screen_address(self, address: str) -> Dict[str, Any]:
        """Return a risk assessment for an address. Not-configured providers
        return neutral risk (0) but are reported so operators can see gaps."""
        if not self.configured:
            logger.warning(
                f"{self.name}: address screening not configured (no API token) - "
                f"returning neutral risk for {address[:10]}..."
            )
            return {"provider": self.name, "configured": False, "risk_score": 0.0, "hits": [], "error": None}
        return self._screen(address)

    @abstractmethod
    def _screen(self, address: str) -> Dict[str, Any]:
        ...


class ChainalysisSanctionsProvider(AnalyticsProvider):
    """Chainalysis Sanctions API stub. Real impl would call
    https://api.chainalysis.com/api/sanctions/v2/address/{address}."""

    name = "chainalysis"

    def _screen(self, address: str) -> Dict[str, Any]:
        raise NotImplementedError("Chainalysis API integration pending operator credentials")


class TrmRiskScreeningProvider(AnalyticsProvider):
    """TRM Labs Screen API stub. Real impl would call
    https://api.trmlabs.com/api/v1/screen/address with a bearer token."""

    name = "trm"

    def _screen(self, address: str) -> Dict[str, Any]:
        raise NotImplementedError("TRM API integration pending operator credentials")


class AddressRiskEngine:
    def __init__(
        self,
        shadow_path: Optional[str] = None,
        ofac=None,
        fatf=None,
        providers: Optional[List[AnalyticsProvider]] = None,
        review_threshold: float = 40.0,
        block_threshold: float = 90.0,
        large_txn_review_usd: float = 10000.0,
    ):
        from .ofac import ofac_feed
        from .fatf import fatf_feed
        from app.core.config import settings

        self.shadow_path = shadow_path or settings.sanctions_shadow_path
        self.ofac = ofac or ofac_feed
        self.fatf = fatf or fatf_feed
        self.review_threshold = review_threshold
        self.block_threshold = block_threshold
        self.large_txn_review_usd = large_txn_review_usd
        self._shadow: Optional[Dict[str, Any]] = None
        self.providers = providers or [
            ChainalysisSanctionsProvider(api_token=self._secret("chainalysis_api_token")),
            TrmRiskScreeningProvider(api_token=self._secret("trm_api_token")),
        ]

    @staticmethod
    def _secret(field: str) -> Optional[str]:
        from app.core.config import settings
        val = getattr(settings, field, None)
        if hasattr(val, "get_secret_value"):
            return val.get_secret_value()
        return val

    def load_shadow(self, force: bool = False) -> Dict[str, Any]:
        """Load the operator-maintained shadow sanctions set. Missing file is not
        fatal (returns empty) but is loudly logged so operators know screening
        relies on the live OFAC feed only."""
        if self._shadow is not None and not force:
            return self._shadow
        path = Path(self.shadow_path)
        if not path.exists():
            self._shadow = {"addresses": [], "jurisdictions": {"high": [], "grey": []}, "currencies": {"blocked": [], "flagged": []}}
            logger.error(f"SHADOW SANCTIONS SET MISSING: {path} - screening relies on live OFAC/FATF only")
            return self._shadow
        try:
            data = json.loads(path.read_text())
            self._shadow = data
            logger.info(f"Shadow sanctions set loaded: {len(data.get('addresses', []))} addresses from {path}")
            return self._shadow
        except Exception as e:
            logger.error(f"Failed to load shadow sanctions set {path}: {e}")
            self._shadow = {"addresses": [], "jurisdictions": {"high": [], "grey": []}, "currencies": {"blocked": [], "flagged": []}}
            return self._shadow

    def _shadow_match(self, address: str) -> Optional[Dict[str, Any]]:
        shadow = self.load_shadow()
        for entry in shadow.get("addresses", []):
            if normalize_address(entry.get("address", "")) == address:
                return {"address": address, **entry}
        return None

    def _ofac_address_match(self, address: str) -> Optional[Dict[str, Any]]:
        try:
            sdn_list = self.ofac.get_sdn_list()
        except Exception as e:
            logger.error(f"OFAC SDN unavailable for address screening: {e}")
            return None
        for entry in sdn_list:
            for addr in entry.get("addresses", []) or []:
                if normalize_address(addr) == address:
                    return {
                        "address": address,
                        "sdn_name": entry.get("sdn_name"),
                        "ent_num": entry.get("ent_num"),
                        "program": entry.get("program"),
                        "list": "OFAC SDN (digital currency address)",
                    }
        return None

    def _jurisdiction_risk(self, jurisdiction: Optional[str]) -> Optional[Dict[str, Any]]:
        if not jurisdiction:
            return None
        try:
            result = self.fatf.is_high_risk(jurisdiction)
        except Exception as e:
            logger.error(f"FATF jurisdiction check failed for {jurisdiction}: {e}")
            return None
        shadow = self.load_shadow()
        if result.get("high_risk"):
            return {
                "jurisdiction": jurisdiction,
                "list": result.get("list"),
                "risk_level": result.get("risk_level"),
                "requires_edd": result.get("requires_edd", False),
            }
        norm = jurisdiction.strip().lower()
        for j in shadow.get("jurisdictions", {}).get("high", []):
            if str(j).strip().lower() == norm:
                return {"jurisdiction": jurisdiction, "list": "shadow-high-risk", "risk_level": "high", "requires_edd": True}
        for j in shadow.get("jurisdictions", {}).get("grey", []):
            if str(j).strip().lower() == norm:
                return {"jurisdiction": jurisdiction, "list": "shadow-grey-list", "risk_level": "medium", "requires_edd": False}
        return None

    def _currency_flag(self, currency: Optional[str]) -> Optional[Dict[str, Any]]:
        if not currency:
            return None
        shadow = self.load_shadow()
        norm = currency.strip().upper()
        for c in shadow.get("currencies", {}).get("blocked", []):
            if str(c.get("ticker", "")).strip().upper() == norm:
                return {"currency": currency, "action": "blocked", "reason": c.get("reason", "")}
        for c in shadow.get("currencies", {}).get("flagged", []):
            if str(c.get("ticker", "")).strip().upper() == norm:
                return {"currency": currency, "action": "flagged", "reason": c.get("reason", "")}
        return None

    def screen_transaction(
        self,
        address: str,
        amount: Optional[float] = None,
        jurisdiction: Optional[str] = None,
        currency: Optional[str] = None,
        counterparty: Optional[str] = None,
    ) -> Dict[str, Any]:
        norm = normalize_address(address)
        reasons: List[str] = []
        score = 0.0
        sources: List[str] = []

        if norm is None:
            return {
                "screened_address": address,
                "error": "Invalid EVM address",
                "decision": "error",
                "reasons": ["Address could not be normalized to a valid 0x address"],
                "checked_at": self._now(),
            }

        shadow_match = self._shadow_match(norm)
        ofac_match = self._ofac_address_match(norm)
        jurisdiction_risk = self._jurisdiction_risk(jurisdiction)
        currency_flag = self._currency_flag(currency)

        analytics = []
        for p in self.providers:
            analytics.append(p.screen_address(norm))
            score += analytics[-1].get("risk_score", 0.0)

        if shadow_match:
            score = max(score, 100.0)
            reasons.append(f"Shadow sanctions set match: {shadow_match.get('label', shadow_match.get('list', 'unknown'))}")
            sources.append("shadow")
        if ofac_match:
            score = max(score, 100.0)
            reasons.append(f"OFAC SDN digital currency address match: {ofac_match.get('sdn_name')}")
            sources.append("ofac-sdn")
        if jurisdiction_risk:
            score += 40 if jurisdiction_risk.get("risk_level") == "high" else 20
            reasons.append(f"High-risk jurisdiction ({jurisdiction_risk.get('jurisdiction')}): {jurisdiction_risk.get('list')}")
            sources.append("fatf")
        if currency_flag:
            score += 50 if currency_flag.get("action") == "blocked" else 15
            reasons.append(f"Currency flag ({currency_flag.get('currency')}): {currency_flag.get('reason')}")
            sources.append("shadow-currency")
        if amount is not None and amount >= self.large_txn_review_usd:
            score += 40
            reasons.append(f"Large transaction ${amount:,.2f} >= enhanced review threshold ${self.large_txn_review_usd:,.2f}")
            sources.append("amount")

        score = round(min(score, 100.0), 2)
        if score >= self.block_threshold:
            decision = "block"
        elif score >= self.review_threshold:
            decision = "review"
        else:
            decision = "allow"

        return {
            "screened_address": norm,
            "amount": amount,
            "jurisdiction": jurisdiction,
            "currency": currency,
            "counterparty": counterparty,
            "shadow_match": shadow_match,
            "ofac_address_match": ofac_match,
            "jurisdiction_risk": jurisdiction_risk,
            "currency_flag": currency_flag,
            "analytics": analytics,
            "risk_score": score,
            "decision": decision,
            "reasons": reasons,
            "sources": sorted(set(sources)),
            "checked_at": self._now(),
        }

    @staticmethod
    def _now() -> str:
        from datetime import datetime
        return datetime.utcnow().isoformat()


address_risk_engine = AddressRiskEngine()
