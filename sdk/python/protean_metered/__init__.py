# Protean Metered Client SDK (Python)
#
# Minimal, dependency-light client for the metered token-licensing API.
#   * POST /v1/transactions/analyze   - 1 token: score + SHAP + ZK + compliance
#   * POST /v1/compliance/check       - 1 token: OFAC/FATF party screening
#   * POST /v1/entitlement            - 0 tokens: balance / expiry / license offer
#   * POST /v1/webhooks/register      - 0 tokens: signed delivery subscription
#
# When the pilot grant is exhausted every paid call returns HTTP 402 with a
# license offer in the body - handle it to surface "license required" to billing.
"""Protean metered API client.

```python
from protean_metered import ProteanClient, ProteanError, EntitlementExhausted

client = ProteanClient(api_key="pk_live_...", base_url="https://api.protean.sh")

try:
    verdict = client.analyze(
        type="payment", value_eth=5000.0, is_protected_user=1,
        mode="defense",
        parties=[{"name": "ACME Corp", "country": "US"}],
    )
    print(verdict["decision"], verdict["risk_score"], verdict["zk_status"])
except EntitlementExhausted as e:
    print("pilot exhausted, license offer:", e.offer)  # send to billing
```
"""
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class ProteanError(Exception):
    pass


class EntitlementExhausted(ProteanError):
    """HTTP 402 - pilot pool exhausted / expired. Carries the license offer."""

    def __init__(self, message: str, offer: Optional[Dict[str, Any]] = None,
                 headers: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.offer = offer
        self.headers = headers or {}


class ProteanClient:
    def __init__(self, api_key: str, base_url: str = "https://api.protean.sh",
                 timeout: float = 120.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    def analyze(self, type: str = "payment", value_eth: float = 0.0,
                gas_price_gwei: float = 0.0, slippage_bps: float = 0.0,
                pool_liquidity_eth: float = 0.0, is_protected_user: int = 1,
                mode: str = "defense", tx_hash: str = "",
                parties: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Full transaction analysis (1 token). ZK proof is included."""
        body = {
            "type": type, "value_eth": value_eth, "gas_price_gwei": gas_price_gwei,
            "slippage_bps": slippage_bps, "pool_liquidity_eth": pool_liquidity_eth,
            "is_protected_user": is_protected_user, "mode": mode, "tx_hash": tx_hash,
            "parties": parties or [],
        }
        return self._request("POST", "/v1/transactions/analyze", body)

    def compliance_check(self, name: Optional[str] = None,
                         address: Optional[str] = None,
                         country: Optional[str] = None) -> Dict[str, Any]:
        """Screen a party against sanctions/watchlists (1 token)."""
        return self._request("POST", "/v1/compliance/check",
                             {"name": name, "address": address, "country": country})

    def entitlement(self) -> Dict[str, Any]:
        """Token balance / expiry / license offer (0 tokens)."""
        return self._request("POST", "/v1/entitlement", {})

    def register_webhook(self, url: str, events: Optional[List[str]] = None) -> Dict[str, Any]:
        """Subscribe to signed decision delivery. Returns the HMAC secret."""
        return self._request("POST", "/v1/webhooks/register",
                             {"url": url, "events": events or ["tx.analyzed", "compliance.checked"]})

    def list_webhooks(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/webhooks", None)

    # ------------------------------------------------------------------ #
    def _request(self, method: str, path: str, body: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"X-API-Key": self.api_key, "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8")
            detail = None
            try:
                detail = json.loads(raw)
            except Exception:
                detail = {"message": raw}
            if e.code == 402:
                offer = detail.get("detail", {}).get("offer") if isinstance(detail.get("detail"), dict) else None
                raise EntitlementExhausted(str(detail.get("detail") or detail), offer, dict(e.headers))
            raise ProteanError(f"{method} {path} -> {e.code}: {detail}")


def verify_webhook_signature(secret: str, body: bytes, signature: str,
                             timestamp: Optional[str] = None,
                             max_age_seconds: int = 300) -> bool:
    """Verify an X-Protean-Signature header against the raw request body.

    The signature is `sha256=<hex>` of the HMAC-SHA256 of the exact JSON body
    (compact, sorted keys) using the webhook secret. Optional replay protection
    via X-Protean-Timestamp.
    """
    if not signature.startswith("sha256="):
        return False
    if timestamp is not None:
        try:
            if abs(int(time.time()) - int(timestamp)) > max_age_seconds:
                return False
        except (ValueError, TypeError):
            return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


__all__ = ["ProteanClient", "ProteanError", "EntitlementExhausted", "verify_webhook_signature"]
