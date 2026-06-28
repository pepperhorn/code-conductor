from __future__ import annotations

from telegram import Bot
from telegram.error import TelegramError

from conductor.config import AppConfig
from conductor.session_footer import SessionStats, render_session_footer
from conductor.sessions.registry import SessionRecord


class ControlNotifier:
    def __init__(self, config: AppConfig, bot: Bot):
        self.config = config
        self.bot = bot

    async def slot_activity(
        self,
        session: SessionRecord,
        *,
        title: str,
        detail: str = "",
        stats: SessionStats | None = None,
    ) -> None:
        text = title
        if detail:
            text += f"\n{detail}"
        text += render_session_footer(self.config.session_footer, session, stats)
        for chat_id in self.config.telegram.allowed_chat_ids:
            try:
                await self.bot.send_message(chat_id=chat_id, text=text)
            except TelegramError:
                continue
