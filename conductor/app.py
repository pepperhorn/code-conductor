from __future__ import annotations

import asyncio
import logging

from conductor.config import AppConfig

log = logging.getLogger(__name__)


async def run_app(config: AppConfig) -> None:
    """Wire runtime services. Filled out by the Telegram/control-plane implementation."""
    log.info(
        "loaded config: project_root=%s channel_slots=%s",
        config.project.root,
        config.channels.slot_count,
    )
    stop = asyncio.Event()
    await stop.wait()
