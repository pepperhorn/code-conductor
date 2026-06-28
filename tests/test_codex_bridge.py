from __future__ import annotations

from conductor.bridges.codex_telegram import (
    _attachment_prompt,
    _clip,
    _codex_is_working,
    _safe_filename,
    _status_text,
    parse_codex_stats,
)
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


def test_codex_working_detection_checks_tail() -> None:
    assert _codex_is_working("hello\n• Working (4s • esc to interrupt)")
    assert not _codex_is_working("done\n› next prompt")


def test_bridge_control_details_are_metadata_only() -> None:
    request_detail = "Forwarded message to Codex."
    response_detail = "Codex response sent to slot bot."

    assert "Any wip" not in request_detail
    assert "Ran " not in response_detail


def test_parse_codex_stats_from_status_line() -> None:
    stats = parse_codex_stats(
        "  gpt-5.5 medium · ~/brother · never · Context 91% left · "
        "Context 9% used · 5h"
    )

    assert stats.model == "gpt-5.5 medium"
    assert stats.context_remaining == "91% left"
    assert stats.context_used == "9% used"
    assert stats.context_limit == "5h"


def test_attachment_prompt_includes_path_and_caption() -> None:
    prompt = _attachment_prompt("what is this?", "/tmp/file.pdf")

    assert "User attached a file at: /tmp/file.pdf" in prompt
    assert "what is this?" in prompt


def test_safe_filename_strips_unsafe_chars() -> None:
    assert _safe_filename("../../bad file.pdf") == "bad-file.pdf"
    assert _safe_filename("!!!") == "attachment"


def test_closed_session_message_copy_is_clear() -> None:
    text = "This Codex slot session is closed. Start a new session from @phconductorbot."

    assert "closed" in text
    assert "@phconductorbot" in text
