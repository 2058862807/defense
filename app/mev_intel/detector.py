"""
Enterprise MEV Attacker Intelligence - Defensive Surveillance
- Consumes the real mempool feed (parsed transactions from MempoolConnectorEnterprise)
- Detects sandwich attempts: [front-run swap] -> [victim swap] -> [back-run swap] on same pool
- Fingerprints attacker bots: address, gas premium bidding, patterns, victims affected
- Provides real-time attribution intel to the defense bot and dashboard
- NO attack execution - defensive intelligence only

Government standard: audit logged, PII redacted, deterministic (no random)
"""
import logging
import time
import threading
from collections import deque, defaultdict
from typing import Dict, Any, List, Optional

from app.core.logging import audit_log

logger = logging.getLogger(__name__)

# Sandwich detection window and thresholds (defensive defaults)
DEFAULT_WINDOW_SECONDS = 30.0
DEFAULT_GAS_MULTIPLIER = 1.5      # front/back-run gas must be >= 1.5x pool average
DEFAULT_MIN_VICTIM_VALUE_ETH = 0.1
DEFAULT_MAX_SANDWICH_SPAN = 12.0  # seconds between front-run and back-run

PII_REDACTED = "0x...->[REDACTED]"


class AttackerIntelDetector:
    """
    Tracks pending txs per pool and fingerprints addresses that run
    sandwich/front-run patterns against users.

    Defensive: outputs attribution + risk intel only. Never builds or submits
    transactions itself.
    """

    def __init__(
        self,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        gas_multiplier: float = DEFAULT_GAS_MULTIPLIER,
        min_victim_value_eth: float = DEFAULT_MIN_VICTIM_VALUE_ETH,
        max_sandwich_span: float = DEFAULT_MAX_SANDWICH_SPAN,
    ):
        self.window_seconds = window_seconds
        self.gas_multiplier = gas_multiplier
        self.min_victim_value_eth = min_victim_value_eth
        self.max_sandwich_span = max_sandwich_span

        # per-pool rolling window: pool -> deque of tx dicts
        self._pool_window: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))

        # per-attacker fingerprints: address -> stats dict
        self._attackers: Dict[str, Dict[str, Any]] = {}

        self._sandwich_attempts: deque = deque(maxlen=200)

        self._lock = threading.RLock()
        self._seq = 0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def analyze_pending_tx(self, tx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Feed one real mempool tx (parsed by MempoolConnectorEnterprise).
        Returns a sandwich-attempt report if the tx completes an attack
        pattern, else None. Never executes anything.
        """
        if not tx:
            return None

        pool = self._resolve_pool(tx)
        if not pool:
            return None

        ts = float(tx.get("timestamp") or time.time())
        gas = float(tx.get("gas_price_gwei") or 0.0)
        sender = tx.get("user") or tx.get("from") or ""
        value = float(tx.get("value_eth") or 0.0)
        tx_type = tx.get("type") or "unknown"
        is_swap = tx_type == "swap"

        with self._lock:
            self._prune_window(pool, ts)

            window = self._pool_window[pool]
            avg_gas = self._average_gas(window)

            record = {
                "hash": tx.get("hash") or "",
                "sender": sender,
                "to": pool,
                "gas_price_gwei": gas,
                "value_eth": value,
                "type": tx_type,
                "ts": ts,
            }
            window.append(record)

            # Fingerprint sender if it shows MEV-bot bidding behavior
            self._fingerprint_sender(record, avg_gas)

            # Look for a completed sandwich: this tx is the back-run
            if is_swap and gas >= avg_gas * self.gas_multiplier and len(window) >= 3:
                attempt = self._match_sandwich(record, window, avg_gas)
                if attempt:
                    self._record_attempt(attempt)
                    return attempt

        return None

    def get_attackers(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Snapshot of fingerprinted attacker bots, highest score first."""
        with self._lock:
            ranked = sorted(
                self._attackers.values(),
                key=lambda a: (a["attacker_score"], a["sandwich_count"]),
                reverse=True,
            )
            return ranked[:limit]

    def get_sandwich_attempts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Most recent detected sandwich attempts, newest first."""
        with self._lock:
            attempts = list(self._sandwich_attempts)
            attempts.sort(key=lambda a: a["timestamp"], reverse=True)
            return attempts[:limit]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_pools": len(self._pool_window),
                "fingerprinted_attackers": len(self._attackers),
                "sandwich_attempts_detected": len(self._sandwich_attempts),
            }

    def reset(self):
        with self._lock:
            self._pool_window.clear()
            self._attackers.clear()
            self._sandwich_attempts.clear()

    # ------------------------------------------------------------------ #
    # Detection internals
    # ------------------------------------------------------------------ #
    def _resolve_pool(self, tx: Dict[str, Any]) -> Optional[str]:
        to_addr = tx.get("to")
        if to_addr and isinstance(to_addr, str) and to_addr.startswith("0x"):
            return to_addr.lower()
        decoded = tx.get("decoded_calldata") or {}
        token = decoded.get("token_out") or decoded.get("token_in")
        if token and isinstance(token, str) and token.startswith("0x"):
            return token.lower()
        return None

    def _average_gas(self, window: deque) -> float:
        if not window:
            return 0.0
        gasses = [r["gas_price_gwei"] for r in window if r["gas_price_gwei"] > 0]
        if not gasses:
            return 0.0
        return sum(gasses) / len(gasses)

    def _prune_window(self, pool: str, now: float):
        window = self._pool_window[pool]
        while window and now - window[0]["ts"] > self.window_seconds:
            window.popleft()

    def _match_sandwich(self, backrun: Dict[str, Any], window: deque, avg_gas: float) -> Optional[Dict[str, Any]]:
        """
        Given the arriving back-run tx, scan earlier records in the same pool
        for [front-run by same sender, victim swap by someone else].
        """
        backrun_ts = backrun["ts"]
        attacker = backrun["sender"]
        if not attacker:
            return None

        # All prior records in window that could be the front-run by same sender
        window_list = list(window)
        for i, frontrun in enumerate(window_list):
            if frontrun is backrun:
                continue
            if frontrun["sender"] != attacker:
                continue
            if not frontrun["type"] == "swap":
                continue
            if frontrun["ts"] > backrun_ts:
                continue
            # Victim must sit between front-run and back-run
            for victim in window_list[i + 1:]:
                if victim is backrun:
                    break
                if victim["sender"] == attacker:
                    continue
                if victim["type"] != "swap":
                    continue
                if not (frontrun["ts"] <= victim["ts"] <= backrun_ts):
                    continue
                span = backrun_ts - frontrun["ts"]
                if span > self.max_sandwich_span:
                    continue
                victim_value = victim["value_eth"]
                if victim_value < self.min_victim_value_eth:
                    continue
                # Front/back-run gas premium over victim's gas confirms attack intent
                if frontrun["gas_price_gwei"] < victim["gas_price_gwei"]:
                    continue

                return {
                    "attacker": attacker,
                    "pool": backrun["to"],
                    "victim": victim["sender"],
                    "victim_tx": victim["hash"],
                    "victim_value_eth": victim_value,
                    "front_run_tx": frontrun["hash"],
                    "back_run_tx": backrun["hash"],
                    "front_run_gas_gwei": frontrun["gas_price_gwei"],
                    "victim_gas_gwei": victim["gas_price_gwei"],
                    "back_run_gas_gwei": backrun["gas_price_gwei"],
                    "span_seconds": round(span, 3),
                    "timestamp": backrun_ts,
                }
        return None

    def _fingerprint_sender(self, record: Dict[str, Any], avg_gas: float):
        sender = record["sender"]
        if not sender:
            return

        # Only fingerprint MEV-bot behavior: sustained priority gas bidding or a
        # completed attack. Normal users paying market gas are not "attackers".
        bot_like = avg_gas > 0 and record["gas_price_gwei"] >= avg_gas * 1.2
        if not bot_like and sender not in self._attackers:
            return

        fp = self._attackers.setdefault(sender, {
            "address": sender,
            "tx_count": 0,
            "sandwich_count": 0,
            "pattern_counts": {},
            "avg_gas_premium_multiplier": 0.0,
            "total_victim_value_eth": 0.0,
            "first_seen": record["ts"],
            "last_seen": record["ts"],
            "attacker_score": 0.0,
            "risk_level": "LOW",
        })

        fp["tx_count"] += 1
        fp["last_seen"] = max(fp["last_seen"], record["ts"])
        fp["first_seen"] = min(fp["first_seen"], record["ts"])

        pattern = record.get("type") or "unknown"
        fp["pattern_counts"][pattern] = fp["pattern_counts"].get(pattern, 0) + 1

        if avg_gas > 0:
            multiplier = record["gas_price_gwei"] / avg_gas
            prev = fp["avg_gas_premium_multiplier"]
            n = fp["tx_count"]
            fp["avg_gas_premium_multiplier"] = prev + (multiplier - prev) / n

        self._update_score(fp)

    def _record_attempt(self, attempt: Dict[str, Any]):
        attempt_id = f"{attempt['front_run_tx'][-12:]}-{attempt['back_run_tx'][-12:]}"
        attempt["attempt_id"] = attempt_id
        self._sandwich_attempts.append(attempt)

        attacker = attempt["attacker"]
        with self._lock:
            fp = self._attackers.get(attacker)
            if fp:
                fp["sandwich_count"] += 1
                fp["total_victim_value_eth"] += attempt["victim_value_eth"]
                fp["pattern_counts"]["sandwich"] = fp["pattern_counts"].get("sandwich", 0) + 1
                fp["last_seen"] = max(fp["last_seen"], attempt["timestamp"])
                self._update_score(fp)

        audit_log(
            event_type="MEV_SANDWICH_DETECTED",
            actor="mev-intel",
            action="attribution",
            resource=attempt["pool"],
            result="DETECTED",
            metadata={
                "attacker": PII_REDACTED,
                "victim_value_eth": attempt["victim_value_eth"],
                "span_seconds": attempt["span_seconds"],
            },
        )
        logger.warning(
            f"[MEV-INTEL] Sandwich attempt on {attempt['pool']} "
            f"attacker={attacker} victim_value={attempt['victim_value_eth']} ETH "
            f"span={attempt['span_seconds']}s"
        )

    def _update_score(self, fp: Dict[str, Any]):
        """
        Deterministic attacker score 0-1 from observed evidence:
        - sandwich_count: strongest signal
        - gas premium multiplier
        - number of victims / value affected
        - recency and tx count
        """
        sandwich = float(fp["sandwich_count"])
        premium = float(fp["avg_gas_premium_multiplier"])
        victims = float(fp["pattern_counts"].get("swap", 0))
        tx_count = float(fp["tx_count"])

        score = 0.0
        score += min(sandwich / 5.0, 1.0) * 0.5
        score += min(max(premium - 1.0, 0.0) / 1.0, 1.0) * 0.25
        score += min(victims / 20.0, 1.0) * 0.15
        score += min(tx_count / 50.0, 1.0) * 0.10

        fp["attacker_score"] = round(score, 4)
        fp["risk_level"] = (
            "CRITICAL" if score >= 0.7 else
            "HIGH" if score >= 0.5 else
            "MEDIUM" if score >= 0.3 else
            "LOW"
        )


# Shared singleton wired into the API / dashboard
intel_detector = AttackerIntelDetector()
