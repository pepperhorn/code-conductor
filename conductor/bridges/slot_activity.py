from __future__ import annotations

import asyncio
import hashlib
import logging

from conductor.bridges.notifier import ControlNotifier
from conductor.sessions.registry import Registry
from conductor.sessions.tmux import Tmux

log = logging.getLogger(__name__)


class SlotActivityWatcher:
    """Best-effort activity watcher for native slot integrations Conductor does not own."""

    def __init__(
        self,
        registry: Registry,
        notifier: ControlNotifier,
        tmux: Tmux | None = None,
        *,
        interval_seconds: int = 15,
        cooldown_seconds: int = 60,
    ):
        self.registry = registry
        self.notifier = notifier
        self.tmux = tmux or Tmux()
        self.interval_seconds = interval_seconds
        self.cooldown_seconds = cooldown_seconds
        self._pane_hashes: dict[str, str] = {}
        self._last_announced: dict[str, float] = {}

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass

    async def tick(self) -> None:
        sessions = await self.registry.list_sessions(statuses={"live", "idle"})
        watched = {
            session.id: session
            for session in sessions
            if session.cli == "claude" and session.bot_slot
        }
        for session_id in list(self._pane_hashes):
            if session_id not in watched:
                self._pane_hashes.pop(session_id, None)
                self._last_announced.pop(session_id, None)

        now = asyncio.get_running_loop().time()
        for session in watched.values():
            try:
                pane = await self.tmux.capture(session.tmux_target)
            except Exception:
                log.exception("failed to capture pane for slot activity")
                continue
            digest = hashlib.sha256(pane.encode("utf-8", errors="ignore")).hexdigest()
            previous = self._pane_hashes.get(session.id)
            self._pane_hashes[session.id] = digest
            if previous is None or previous == digest:
                continue
            last = self._last_announced.get(session.id, 0)
            if now - last < self.cooldown_seconds:
                continue
            self._last_announced[session.id] = now
            await self.notifier.slot_activity(
                session,
                title=f"best-effort slot activity: @{session.bot_slot}",
                detail="Claude native slot pane changed.",
            )
