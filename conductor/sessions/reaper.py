from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from conductor.config import AppConfig
from conductor.sessions.manager import SessionManager
from conductor.sessions.registry import Registry

log = logging.getLogger(__name__)


class Reaper:
    def __init__(
        self,
        config: AppConfig,
        registry: Registry,
        manager: SessionManager,
        *,
        interval_seconds: int = 60,
    ):
        self.config = config
        self.registry = registry
        self.manager = manager
        self.interval_seconds = interval_seconds

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass

    async def tick(self) -> None:
        await self.manager.reconcile()
        sessions = await self.registry.list_sessions(statuses={"live", "idle"})
        now = datetime.now(UTC)
        for session in sessions:
            last_raw = session.last_activity or session.started_at
            try:
                last = datetime.fromisoformat(last_raw)
            except ValueError:
                continue
            idle_minutes = (now - last).total_seconds() / 60
            if idle_minutes >= self.config.defaults.idle_timeout_minutes:
                log.info("reaping idle session %s", session.id)
                await self.manager.stop(session.id)
            elif (
                idle_minutes >= self.config.defaults.idle_warning_minutes
                and session.status == "live"
            ):
                await self.registry.update_session_status(session.id, "idle")
