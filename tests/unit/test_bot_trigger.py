"""B6 - WS-only bot trigger registry unit tests.

The registry is the fail-closed gate between the shared mempool listener and
the offense/defense bots: nothing is armed by default, only an authorized
operator can arm over a WebSocket, and armed state is per-mode with focus.
"""

import pytest

from app.core.bot_trigger import BotTriggerRegistry, VALID_MODES, DEFAULT_FOCUS


def test_default_state_is_disarmed():
    reg = BotTriggerRegistry()
    assert reg.state() == {"offense": None, "defense": None}
    assert not reg.armed("offense")
    assert not reg.armed("defense")


def test_arm_sets_state_with_actor_and_timestamp():
    reg = BotTriggerRegistry()
    entry = reg.arm("defense", "sandwich", armed_by="ops-bot")
    assert entry["mode"] == "defense"
    assert entry["focus"] == "sandwich"
    assert entry["armed_by"] == "ops-bot"
    assert entry["enabled"] is True
    assert entry["armed_at"] > 0
    assert reg.armed("defense")
    assert not reg.armed("offense")


def test_arm_defaults_focus():
    reg = BotTriggerRegistry()
    entry = reg.arm("offense")
    assert entry["focus"] == DEFAULT_FOCUS


def test_arm_is_case_insensitive():
    reg = BotTriggerRegistry()
    reg.arm("DEFENSE", "AUTO", armed_by="ops")
    assert reg.armed("defense")
    assert reg.focus("DEFENSE") == "auto"


def test_unknown_mode_raises():
    reg = BotTriggerRegistry()
    with pytest.raises(ValueError):
        reg.arm("crypto-miner")
    with pytest.raises(ValueError):
        reg.disarm("crypto-miner")


def test_rearm_overwrites_and_updates_actor():
    reg = BotTriggerRegistry()
    reg.arm("offense", "arbitrage", armed_by="alice")
    reg.arm("offense", "liquidation", armed_by="bob")
    entry = reg.state()["offense"]
    assert entry["focus"] == "liquidation"
    assert entry["armed_by"] == "bob"


def test_disarm_single_mode():
    reg = BotTriggerRegistry()
    reg.arm("offense")
    reg.arm("defense")
    reg.disarm("offense")
    assert not reg.armed("offense")
    assert reg.armed("defense")


def test_disarm_all():
    reg = BotTriggerRegistry()
    reg.arm("offense")
    reg.arm("defense")
    reg.disarm()
    assert reg.state() == {"offense": None, "defense": None}


def test_state_is_snapshot_not_shared_reference():
    reg = BotTriggerRegistry()
    reg.arm("offense")
    snapshot = reg.state()
    snapshot["offense"]["focus"] = "mutated"
    assert reg.focus("offense") != "mutated"


def test_armed_unknown_mode_is_false():
    reg = BotTriggerRegistry()
    assert not reg.armed("non-existent")


def test_valid_modes():
    assert set(VALID_MODES) == {"offense", "defense"}


def test_bot_status_broadcast_delivers_to_ws_clients():
    """Regression: _broadcast_bot_status must await send_json (previously the
    coroutine was created but never awaited, so arm/disarm confirmations and
    bot_status broadcasts were silently dropped)."""
    import asyncio
    import app.main as m

    calls = []

    class FakeConn:
        async def send_json(self, msg):
            calls.append(msg)

    async def _run():
        m.manager.active_connections.clear()
        m.dashboard_manager.active_connections.clear()
        conn = FakeConn()
        m.dashboard_manager.active_connections.append(conn)
        await m._broadcast_bot_status({"offense": None, "defense": None})

    asyncio.run(_run())
    assert len(calls) == 1
    assert calls[0]["type"] == "bot_status"
    assert calls[0]["bots"] == {"offense": None, "defense": None}
