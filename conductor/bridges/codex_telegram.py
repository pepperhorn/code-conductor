from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from telegram import Bot, Update
from telegram.error import NetworkError, TelegramError

from conductor.bridges.notifier import ControlNotifier
from conductor.config import AppConfig
from conductor.session_footer import SessionStats
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
        text = (message.text or message.caption or "").strip()
        attachment = await self._download_attachment(bot, session, slot, update)
        if attachment:
            text = _attachment_prompt(text, attachment)
        elif not text:
            await message.reply_text("Send text or an attachment to forward it to Codex.")
            return
        if text in {"/start", "/status"}:
            await message.reply_text(_status_text(session, slot))
            return
        if text == "/snapshot":
            await message.reply_text(_clip(await self.tmux.capture(session.tmux_target)))
            return
        await message.reply_text("Sending to Codex...")
        before = await self.tmux.capture(session.tmux_target)
        await self.notifier.slot_activity(
            session,
            title=f"slot request: @{slot.name}",
            detail="Forwarded message to Codex.",
            stats=parse_codex_stats(before),
        )
        await self.tmux.send_text(session.tmux_target, text)
        pane = await self._wait_for_codex_response(session.tmux_target, before)
        response = _clip(pane)
        await bot.send_message(chat_id=chat.id, text=response)
        await self.notifier.slot_activity(
            session,
            title=f"slot response: @{slot.name}",
            detail="Codex response sent to slot bot.",
            stats=parse_codex_stats(pane),
        )

    async def _download_attachment(
        self,
        bot: Bot,
        session: SessionRecord,
        slot: BotSlotRecord,
        update: Update,
    ) -> Path | None:
        message = update.effective_message
        if message is None:
            return None
        file_id = None
        filename = None
        if message.document:
            file_id = message.document.file_id
            filename = message.document.file_name
        elif message.photo:
            photo = message.photo[-1]
            file_id = photo.file_id
            filename = f"photo-{photo.file_unique_id}.jpg"
        elif message.video:
            file_id = message.video.file_id
            filename = message.video.file_name or f"video-{message.video.file_unique_id}.mp4"
        elif message.audio:
            file_id = message.audio.file_id
            filename = message.audio.file_name or f"audio-{message.audio.file_unique_id}"
        elif message.voice:
            file_id = message.voice.file_id
            filename = f"voice-{message.voice.file_unique_id}.ogg"
        if not file_id:
            return None

        safe_name = _safe_filename(filename or f"attachment-{uuid4().hex}")
        inbox = (
            Path.home()
            / ".conductor"
            / "slots"
            / _safe_filename(slot.name)
            / session.id[:8]
            / "inbox"
        )
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"{uuid4().hex}-{safe_name}"
        telegram_file = await bot.get_file(file_id)
        await telegram_file.download_to_drive(custom_path=path)
        return path

    async def _wait_for_codex_response(
        self,
        tmux_target: str,
        before: str,
        *,
        timeout_seconds: int = 90,
    ) -> str:
        last = before
        for _ in range(timeout_seconds):
            await asyncio.sleep(1)
            pane = await self.tmux.capture(tmux_target)
            if pane != before:
                last = pane
            if pane != before and not _codex_is_working(pane):
                return pane
        return last


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


def _codex_is_working(pane: str) -> bool:
    tail = "\n".join(pane.splitlines()[-12:])
    return "Working (" in tail or "esc to interrupt" in tail


def _attachment_prompt(text: str, path: Path | str) -> str:
    prompt = f"User attached a file at: {path}\nPlease inspect it."
    if text:
        prompt += f"\n\nUser message:\n{text}"
    return prompt


def _safe_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-")
    return safe or "attachment"


def parse_codex_stats(pane: str) -> SessionStats:
    for line in reversed(pane.splitlines()):
        if "Context " not in line:
            continue
        model = _parse_codex_model(line)
        remaining = _regex_group(r"Context\s+(\d+%\s+left)", line)
        used = _regex_group(r"Context\s+\d+%\s+left\s+·\s+Context\s+(\d+%\s+used)", line)
        limit = _regex_group(r"·\s*([^·]*?5h[^·]*)", line)
        return SessionStats(
            model=model or "unknown",
            context_remaining=remaining or "unknown",
            context_used=used or "unknown",
            context_limit=limit or "unknown",
        )
    return SessionStats()


def _parse_codex_model(line: str) -> str | None:
    clean = line.replace("›", "").strip()
    parts = [part.strip() for part in clean.split("·")]
    if not parts:
        return None
    model = parts[0]
    return model if model else None


def _regex_group(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return match.group(1).strip()
