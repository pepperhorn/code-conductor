from __future__ import annotations

import pytest

from conductor.bridges.notifier import ControlNotifier
from conductor.config import (
    AppConfig,
    ChannelsConfig,
    DefaultsConfig,
    ProjectConfig,
    RemoteControlConfig,
    SessionFooterConfig,
    TelegramConfig,
    TrustConfig,
)
from conductor.sessions.registry import SessionRecord


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


@pytest.mark.asyncio
async def test_notifier_sends_footer_to_allowed_chats(tmp_path) -> None:
    config = AppConfig(
        path=tmp_path / "config.toml",
        telegram=TelegramConfig(control_bot_token="TOKEN", allowed_chat_ids=frozenset({123})),
        project=ProjectConfig(root_env="ROOT", root=tmp_path, max_depth=2),
        channels=ChannelsConfig(slot_count_env="SLOTS", slot_count=1),
        defaults=DefaultsConfig(
            cli="claude",
            bypass_permissions=True,
            idle_warning_minutes=25,
            idle_timeout_minutes=30,
        ),
        remote_control=RemoteControlConfig(auto_enable=True),
        session_footer=SessionFooterConfig(enabled=True, template="cli:{cli} slot:{bot_slot}"),
        trust=TrustConfig(auto_confirm_project_trust=True, trusted_root_only=True),
        bot_slots=(),
    )
    session = SessionRecord(
        id="abc12345",
        cli="codex",
        cwd=str(tmp_path),
        tmux_target="tmux:agent",
        data_plane="telegram",
        bot_slot="phcodeslot2_bot",
        status="live",
        started_at="2026-06-28T00:00:00+00:00",
        last_activity=None,
        fired_thresholds=(),
    )
    bot = FakeBot()

    await ControlNotifier(config, bot).slot_activity(session, title="slot response")

    assert bot.messages == [(123, "slot response\n\ncli:codex slot:phcodeslot2_bot")]
