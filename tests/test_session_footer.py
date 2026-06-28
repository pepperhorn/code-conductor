from __future__ import annotations

from conductor.config import SessionFooterConfig
from conductor.session_footer import render_session_footer
from conductor.sessions.registry import SessionRecord


def test_render_session_footer_uses_known_fields() -> None:
    session = SessionRecord(
        id="8d3df576-df0e-45ca-a778-f8554e9ef0b7",
        cli="claude",
        cwd="/home/shaun/crf-framework",
        tmux_target="tmux:agent",
        data_plane="telegram",
        bot_slot="phcodeslot1_bot",
        status="live",
        started_at="2026-06-28T00:00:00+00:00",
        last_activity=None,
        fired_thresholds=(),
    )

    footer = render_session_footer(
        SessionFooterConfig(
            enabled=True,
            template="cli:{cli} cwd:{cwd} session:{session_id} slot:{bot_slot} model:{model}",
        ),
        session,
    )

    assert "cli:claude" in footer
    assert "cwd:/home/shaun/crf-framework" in footer
    assert "session:8d3df576" in footer
    assert "slot:phcodeslot1_bot" in footer
    assert "model:unknown" in footer


def test_render_session_footer_can_be_disabled() -> None:
    session = SessionRecord(
        id="abc",
        cli="claude",
        cwd="/tmp",
        tmux_target="tmux:agent",
        data_plane="app",
        bot_slot=None,
        status="live",
        started_at="2026-06-28T00:00:00+00:00",
        last_activity=None,
        fired_thresholds=(),
    )

    footer = render_session_footer(SessionFooterConfig(enabled=False, template="{cli}"), session)

    assert footer == ""
