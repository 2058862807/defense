"""
FIX protocol adapter (C2 - exchanges / trading desks).

Parses FIX 4.4 tag=value messages (SOH = \\x01 delimited), validates the
trailer checksum, and normalizes order messages (NewOrderSingle 35=D,
ExecutionReport 35=8) into the universal metered analysis request so exchange
order flow can be screened for market-integrity / manipulation risk. Verdicts
map back to a FIX-style response with tags the exchange already understands.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SOH = "\x01"

# FIX 4.4 tags used by the adapter.
TAGS = {
    "35": "msg_type", "49": "sender", "56": "target", "11": "cl_ord_id",
    "1": "account", "55": "symbol", "48": "security_id", "54": "side",
    "38": "order_qty", "44": "price", "59": "time_in_force", "40": "ord_type",
    "60": "transact_time", "58": "text", "10": "checksum", "15": "currency",
    "39": "exec_status", "151": "leaves_qty", "14": "cum_qty",
}

SIDE = {"1": "buy", "2": "sell", "3": "sell_short", "5": "sell_short_exempt"}
ORD_TYPE = {"1": "market", "2": "limit", "3": "stop", "4": "stop_limit", "5": "market_on_close"}


class FIXParseError(ValueError):
    pass


def validate_checksum(msg: str) -> bool:
    """FIX checksum: sum of bytes (excluding checksum field) mod 256."""
    try:
        body, check = msg.rsplit(SOH + "10=", 1)
        check = check.split(SOH)[0]
        total = sum(ord(c) for c in body + SOH)
        return (total % 256) == int(check)
    except Exception:
        return False


def parse_fix(msg: str) -> Dict[str, Any]:
    """Parse a FIX 4.4 message into a dict. SOH or pipe-delimited accepted."""
    delim = SOH if SOH in msg else "|"
    if delim == "|" and SOH not in msg:
        msg = msg.replace("|", SOH)
    fields: Dict[str, str] = {}
    for pair in msg.split(SOH):
        if not pair:
            continue
        if "=" not in pair:
            raise FIXParseError(f"malformed field: {pair!r}")
        tag, _, value = pair.partition("=")
        fields[tag] = value

    out: Dict[str, Any] = {}
    for tag, name in TAGS.items():
        if tag in fields:
            out[name] = fields[tag]
    out["checksum_valid"] = validate_checksum(msg)
    out["msg_type"] = fields.get("35")
    return out


def to_analysis_request(fix: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize an order message into the universal metered analysis request."""
    price = _float(fix.get("price"))
    qty = _float(fix.get("order_qty"))
    notional = (price or 0) * (qty or 0)
    ord_type = ORD_TYPE.get(fix.get("ord_type", ""), "limit")
    # Market orders carry the highest adverse-selection / manipulation risk.
    slippage_bps = 50 if ord_type == "market" else 5
    return {
        "source": "fix",
        "cl_ord_id": fix.get("cl_ord_id"),
        "symbol": fix.get("symbol"),
        "security_id": fix.get("security_id"),
        "side": SIDE.get(fix.get("side", ""), fix.get("side")),
        "ord_type": ord_type,
        "order_qty": qty,
        "price": price,
        "notional": notional,
        "account": fix.get("account"),
        "sender": fix.get("sender"),
        "currency": fix.get("currency"),
        "checksum_valid": fix.get("checksum_valid"),
        "amount": notional,
        "is_protected_user": 1 if fix.get("account") else 0,
        "slippage_bps": slippage_bps,
    }


def verdict_to_fix(verdict: Dict[str, Any], original: Dict[str, Any]) -> str:
    """Map a metered verdict back to a FIX-style execution notice (35=8)."""
    decision = verdict.get("decision")
    status = {"block": "6", "step": "1", "pass": "0"}.get(decision, "1")  # Rejected / Partial / New
    fields = {
        "8": "FIX.4.4",  # BeginString
        "35": "8",  # ExecutionReport
        "49": original.get("sender", "PROTEAN"),
        "56": original.get("target", "EXCHANGE"),
        "11": original.get("cl_ord_id", ""),
        "37": f"PD-{original.get('cl_ord_id', '')}",
        "39": status,
        "150": "8" if decision == "block" else "0",
        "58": f"risk={verdict.get('risk_score'):.2f} decision={decision}",
        "10": "000",
    }
    body = SOH.join(f"{k}={v}" for k, v in fields.items() if k != "10")
    checksum = sum(ord(c) for c in body + SOH) % 256
    return body + SOH + f"10={checksum:03d}"


def _float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
