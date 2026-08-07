"""
WS-only bot trigger registry (B6).

Bots are armed/disarmed exclusively over the /ws and /ws/dashboard channels and
fired by the single shared mempool listener. There is no HTTP polling path and
no per-bot Alchemy subscription. Arming is RBAC-gated by the calling code
(gov-admin / operator). Fail-closed: everything starts disarmed, so no bot can
act until an authorized operator arms it over a WebSocket.
"""
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

VALID_MODES = ("offense", "defense")
DEFAULT_FOCUS = "auto"


class BotTriggerRegistry:
    """Holds per-mode arm state. Reads happen on the mempool listener task
    (and in trigger worker threads); writes happen only on the event loop in
    the WebSocket handlers, so a plain dict is safe here."""

    def __init__(self) -> None:
        self._arms: Dict[str, Optional[Dict[str, Any]]] = {m: None for m in VALID_MODES}

    def arm(self, mode: str, focus: str = DEFAULT_FOCUS, armed_by: Optional[str] = None) -> Dict[str, Any]:
        mode = (mode or "").lower()
        if mode not in VALID_MODES:
            raise ValueError(f"Unknown bot mode: {mode!r} - must be one of {', '.join(VALID_MODES)}")
        focus = (focus or DEFAULT_FOCUS).lower()
        entry = {
            "mode": mode,
            "focus": focus,
            "armed_by": armed_by,
            "armed_at": time.time(),
            "enabled": True,
        }
        self._arms[mode] = entry
        logger.info(f"[BOT-TRIGGER] {mode} armed focus={focus} by={armed_by}")
        return dict(entry)

    def disarm(self, mode: Optional[str] = None) -> Dict[str, Any]:
        if mode is None:
            for m in VALID_MODES:
                self._arms[m] = None
            logger.info("[BOT-TRIGGER] all bots disarmed")
            return self.state()
        mode = (mode or "").lower()
        if mode not in VALID_MODES:
            raise ValueError(f"Unknown bot mode: {mode!r} - must be one of {', '.join(VALID_MODES)}")
        self._arms[mode] = None
        logger.info(f"[BOT-TRIGGER] {mode} disarmed")
        return self.state()

    def state(self) -> Dict[str, Any]:
        return {m: (dict(e) if e else None) for m, e in self._arms.items()}

    def armed(self, mode: str) -> bool:
        entry = self._arms.get((mode or "").lower())
        return bool(entry and entry.get("enabled"))

    def focus(self, mode: str) -> Optional[str]:
        entry = self._arms.get((mode or "").lower())
        return entry.get("focus") if entry else None

    def armed_by(self, mode: str) -> Optional[str]:
        entry = self._arms.get((mode or "").lower())
        return entry.get("armed_by") if entry else None
