"""
Real SSAF (Strategic Shielding & Attribution Framework) monitor.

Mode is computed deterministically from real operational telemetry:
- attribution_blind: sustained MEV bot activity (detected sandwich attempts
  plus fingerprinted attacker bots).
- deferential: attacker fingerprinting active but no completed sandwich yet.
- competitive: normal operation with no MEV bot activity observed.

No random, no hardcoded event streams - only real intel from the live
mempool detector.
"""
import threading
import time
from collections import deque
from typing import Deque, Dict, Any, Optional

WINDOW_SIZE = 50


class SSAFMonitorEnterprise:
    def __init__(self):
        self._lock = threading.RLock()
        self._current_mode = "competitive"
        self._last_magnitude = 0.0
        self._total_triggers = 0
        self._consecutive_blind = 0
        self._modes: Dict[str, int] = {"competitive": 1, "deferential": 0, "attribution_blind": 0}
        self._provenance: Deque[Dict[str, Any]] = deque(maxlen=WINDOW_SIZE)
        self._updated_at: Optional[float] = None

    def update(self, stats: Dict[str, Any]) -> None:
        """
        Feed real intel detector stats on every processed mempool event.
        Deterministic thresholds only.
        """
        with self._lock:
            sandwich = int(stats.get("sandwich_attempts_detected", 0) or 0)
            attackers = int(stats.get("fingerprinted_attackers", 0) or 0)

            magnitude = min(float(sandwich) * 10.0 + float(attackers) * 2.0, 100.0)
            self._last_magnitude = round(magnitude, 2)
            self._updated_at = time.time()

            if sandwich >= 1 and attackers >= 1:
                new_mode = "attribution_blind"
            elif attackers >= 1:
                new_mode = "deferential"
            else:
                new_mode = "competitive"

            if new_mode != self._current_mode:
                self._current_mode = new_mode
                self._total_triggers += 1
                self._provenance.appendleft({
                    "mode": new_mode,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._updated_at)),
                })
                self._modes[new_mode] = self._modes.get(new_mode, 0) + 1
                if new_mode == "attribution_blind":
                    self._consecutive_blind += 1
                else:
                    self._consecutive_blind = 0

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "current_mode": self._current_mode,
                "recent_magnitude": self._last_magnitude,
                "total_triggers": self._total_triggers,
                "recent_provenance": list(self._provenance),
                "modes": dict(self._modes),
                "consecutive_blind": self._consecutive_blind,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._updated_at)) if self._updated_at else None,
                "source": "real_live_intel",
            }


# Shared singleton.
ssaf_monitor = SSAFMonitorEnterprise()
