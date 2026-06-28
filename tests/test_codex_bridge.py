from __future__ import annotations

from conductor.bridges.codex_telegram import _clip, _status_text
from conductor.sessions.registry import BotSlotRecord, SessionRecord


def test_codex_bridge_status_text_mentions_slot() -> None:
    session = SessionRecord(
        id="a57752e0-1234",
        cli="codex",
        cwd="/home/shaun/brother",
        tmux_target="conductor-codex-brother-a57752e0:agent",
        data_plane="telegram",
        bot_slot="phcodeslot2_bot",
        status="live",
        started_at="2026-06-28T00:00:00+00:00",
        last_activity=None,
        fired_thresholds=(),
    )
    slot = BotSlotRecord(name="phcodeslot2_bot", token="TOKEN", leased_session_id=session.id)

    text = _status_text(session, slot)

    assert "Codex bridge ready" in text
    assert "@phcodeslot2_bot" in text
    assert "a57752e0" in text


def test_clip_returns_tail() -> None:
    assert _clip("abc", limit=10) == "abc"
    assert _clip("0123456789abcdef", limit=4) == "cdef"
