from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from conductor.bridges.codex_telegram import CodexTelegramBridge
from conductor.bridges.notifier import ControlNotifier
from conductor.bridges.slot_activity import SlotActivityWatcher
from conductor.config import AppConfig
from conductor.sessions.manager import SessionManager
from conductor.sessions.reaper import Reaper
from conductor.sessions.registry import Registry
from conductor.telegram.control_bot import COMMANDS, build_application

log = logging.getLogger(__name__)


async def run_app(config: AppConfig) -> None:
    """Wire runtime services."""
    log.info(
        "loaded config: project_root=%s channel_slots=%s",
        config.project.root,
        config.channels.slot_count,
    )
    registry = Registry(Path("conductor.sqlite3"))
    await registry.init(config.bot_slots)
    manager = SessionManager(config, registry)
    await manager.reconcile()
    telegram_app = build_application(config, registry, manager)
    reaper = Reaper(config, registry, manager)
    notifier = ControlNotifier(config, telegram_app.bot)
    codex_bridge = CodexTelegramBridge(config, registry, notifier)
    slot_activity = SlotActivityWatcher(registry, notifier)
    stop = asyncio.Event()
    async with telegram_app:
        await telegram_app.start()
        await telegram_app.bot.set_my_commands(list(COMMANDS))
        await telegram_app.updater.start_polling()
        reaper_task = asyncio.create_task(reaper.run(stop))
        bridge_task = asyncio.create_task(codex_bridge.run(stop))
        slot_activity_task = asyncio.create_task(slot_activity.run(stop))
        try:
            await stop.wait()
        finally:
            stop.set()
            reaper_task.cancel()
            bridge_task.cancel()
            slot_activity_task.cancel()
            await telegram_app.updater.stop()
            await telegram_app.stop()
