from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from telegram import Bot, Update
from telegram.error import NetworkError, TelegramError

from conductor.bridges.notifier import ControlNotifier
from conductor.config import AppConfig
from conductor.sessions.registry import BotSlotRecord, Registry, SessionRecord
from conductor.sessions.tmux import Tmux

log = logging.getLogger(__name__)


@dataclass
class BridgeTask:
    session_id: str
    slot_name: str
    task: asyncio.Task[None]


class CodexTelegramBridge:
    def __init__(
        self,
        config: AppConfig,
        registry: Registry,
        notifier: ControlNotifier,
        tmux: Tmux | None = None,
        *,
        scan_interval_seconds: int = 5,
    ):
        self.config = config
        self.registry = registry
        self.notifier = notifier
        self.tmux = tmux or Tmux()
        self.scan_interval_seconds = scan_interval_seconds
        self.tasks: dict[str, BridgeTask] = {}

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.scan()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.scan_interval_seconds)
            except TimeoutError:
                pass
        await self.stop_all()

    async def scan(self) -> None:
        sessions = await self.registry.list_sessions(statuses={"live", "idle", "starting"})
        codex_by_slot = {
            session.bot_slot: session
            for session in sessions
            if session.cli == "codex" and session.bot_slot
        }
        slots = {slot.name: slot for slot in await self.registry.list_slots()}

        for slot_name, bridge in list(self.tasks.items()):
            if slot_name not in codex_by_slot:
                bridge.task.cancel()
                del self.tasks[slot_name]

        for slot_name, session in codex_by_slot.items():
            if slot_name in self.tasks:
                continue
            slot = slots.get(slot_name)
            if slot is None:
                continue
            task = asyncio.create_task(self._poll_slot(session, slot))
            self.tasks[slot_name] = BridgeTask(
                session_id=session.id,
                slot_name=slot_name,
                task=task,
            )

    async def stop_all(self) -> None:
        for bridge in self.tasks.values():
            bridge.task.cancel()
        if self.tasks:
            await asyncio.gather(
                *(bridge.task for bridge in self.tasks.values()),
                return_exceptions=True,
            )
        self.tasks.clear()

    async def _poll_slot(self, session: SessionRecord, slot: BotSlotRecord) -> None:
        bot = Bot(slot.token)
        offset = 0
        log.info("starting Codex Telegram bridge slot=%s session=%s", slot.name, session.id)
        while True:
            try:
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=20,
                    allowed_updates=["message"],
                )
            except NetworkError:
                await asyncio.sleep(3)
                continue
            except TelegramError:
                log.exception("Codex bridge polling failed for slot=%s", slot.name)
                await asyncio.sleep(10)
                continue
            for update in updates:
                offset = max(offset, update.update_id + 1)
                await self._handle_update(bot, session, slot, update)

    async def _handle_update(
        self,
        bot: Bot,
        session: SessionRecord,
        slot: BotSlotRecord,
        update: Update,
    ) -> None:
        message = update.effective_message
        chat = update.effective_chat
        if message is None or chat is None:
            return
        if chat.id not in self.config.telegram.allowed_chat_ids:
            return
        text = (message.text or "").strip()
        if not text:
            await message.reply_text("Send text to forward it to Codex.")
            return
        if text in {"/start", "/status"}:
            await message.reply_text(_status_text(session, slot))
            return
        if text == "/snapshot":
            await message.reply_text(_clip(await self.tmux.capture(session.tmux_target)))
            return
        await message.reply_text("Sending to Codex...")
        await self.notifier.slot_activity(
            session,
            title=f"slot request: @{slot.name}",
            detail=_clip(text, limit=500),
        )
        await self.tmux.send_text(session.tmux_target, text)
        await asyncio.sleep(2)
        pane = await self.tmux.capture(session.tmux_target)
        response = _clip(pane)
        await bot.send_message(chat_id=chat.id, text=response)
        await self.notifier.slot_activity(
            session,
            title=f"slot response: @{slot.name}",
            detail=_clip(response, limit=500),
        )


def _status_text(session: SessionRecord, slot: BotSlotRecord) -> str:
    return (
        "Codex bridge ready.\n"
        f"session: {session.id[:8]}\n"
        f"cwd: {session.cwd}\n"
        f"slot: @{slot.name}\n"
        f"tmux: {session.tmux_target}\n\n"
        "Send a message to forward it to Codex. Use /snapshot for the latest pane."
    )


def _clip(text: str, limit: int = 3900) -> str:
    stripped = text.strip()
    if not stripped:
        return "(no pane output yet)"
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]
