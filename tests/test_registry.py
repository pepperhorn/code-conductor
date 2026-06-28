from __future__ import annotations

from pathlib import Path

import pytest

from conductor.config import BotSlotConfig
from conductor.sessions.registry import Registry, SessionRecord, utc_now_iso


@pytest.mark.asyncio
async def test_registry_seeds_and_leases_slots(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "state.sqlite")
    await registry.init(
        (
            BotSlotConfig(name="slot-1", token="ONE"),
            BotSlotConfig(name="slot-2", token="TWO"),
        )
    )

    lease = await registry.lease_slot("session-1")

    assert lease is not None
    assert lease.name == "slot-1"
    slots = await registry.list_slots()
    assert slots[0].leased_session_id == "session-1"

    await registry.release_session_slot("session-1")
    slots = await registry.list_slots()
    assert slots[0].leased_session_id is None


@pytest.mark.asyncio
async def test_registry_stores_sessions(tmp_path: Path) -> None:
    registry = Registry(tmp_path / "state.sqlite")
    await registry.init((BotSlotConfig(name="slot-1", token="ONE"),))
    record = SessionRecord(
        id="session-1",
        cli="claude",
        cwd=str(tmp_path),
        tmux_target="tmux:agent",
        data_plane="app",
        bot_slot=None,
        status="live",
        started_at=utc_now_iso(),
        last_activity=None,
        fired_thresholds=(50,),
    )

    await registry.create_session(record)
    loaded = await registry.get_session("session-1")

    assert loaded == record
