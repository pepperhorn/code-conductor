from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from conductor.adapters.base import UnsupportedDataPlane
from conductor.adapters.factory import get_adapter
from conductor.channels.bot_pool import BotPool
from conductor.config import AppConfig
from conductor.sessions.registry import Registry, SessionRecord, utc_now_iso
from conductor.sessions.tmux import Tmux, TmuxTarget


@dataclass(frozen=True)
class StartResult:
    session: SessionRecord
    degraded_reason: str | None = None


class SessionManager:
    def __init__(self, config: AppConfig, registry: Registry, tmux: Tmux | None = None):
        self.config = config
        self.registry = registry
        self.tmux = tmux or Tmux()
        self.bot_pool = BotPool(registry)

    async def start(
        self,
        *,
        cwd: Path,
        cli: str,
        data_plane: str,
        bypass: bool,
    ) -> StartResult:
        cwd = cwd.resolve()
        self._validate_cwd(cwd)
        await self._ensure_directory_available(cwd)
        adapter = get_adapter(cli)
        session_id = str(uuid.uuid4())
        bot_slot_name = None
        bot_token = None
        degraded_reason = None
        effective_data_plane = data_plane

        if cli == "codex" and data_plane != "tmux":
            effective_data_plane = "tmux"
            degraded_reason = (
                "Codex does not support Claude app/telegram data planes; use tmux attach."
            )
        elif data_plane in {"telegram", "both"}:
            slot = await self.bot_pool.lease(session_id)
            if slot is None:
                effective_data_plane = "app"
                degraded_reason = "No Telegram slots free; started app-only."
            else:
                bot_slot_name = slot.name
                bot_token = slot.token

        if bypass:
            adapter.settings_bypass_patch(cwd)

        try:
            argv = adapter.build_launch_cmd(
                cwd,
                bypass=bypass,
                data_plane=effective_data_plane,
                bot_token=bot_token,
            )
        except UnsupportedDataPlane as exc:
            if bot_slot_name:
                await self.bot_pool.release(bot_slot_name)
                bot_slot_name = None
            effective_data_plane = "app" if cli == "claude" else "tmux"
            degraded_reason = str(exc)
            argv = adapter.build_launch_cmd(
                cwd,
                bypass=bypass,
                data_plane=effective_data_plane,
                bot_token=None,
            )

        target = TmuxTarget(session=_tmux_session_name(cli, cwd, session_id))
        await self.tmux.start(target, str(cwd), argv)
        record = SessionRecord(
            id=session_id,
            cli=cli,
            cwd=str(cwd),
            tmux_target=target.value,
            data_plane=effective_data_plane,
            bot_slot=bot_slot_name,
            status="live",
            started_at=utc_now_iso(),
            last_activity=utc_now_iso(),
            fired_thresholds=(),
        )
        await self.registry.create_session(record)
        return StartResult(session=record, degraded_reason=degraded_reason)

    async def stop(self, session_id: str) -> bool:
        record = await self.registry.get_session(session_id)
        if record is None:
            return False
        await self.tmux.kill(record.tmux_target)
        await self.bot_pool.release_for_session(session_id)
        await self.registry.update_session_status(session_id, "dead")
        return True

    async def reconcile(self) -> None:
        sessions = await self.registry.list_sessions(
            statuses={"starting", "live", "idle", "stopping"}
        )
        for session in sessions:
            if not await self.tmux.exists(session.tmux_target):
                await self.registry.update_session_status(session.id, "dead")
                await self.bot_pool.release_for_session(session.id)

    def _validate_cwd(self, cwd: Path) -> None:
        root = self.config.project.root
        if ".." in cwd.parts:
            raise ValueError("cwd traversal is not allowed")
        if cwd != root and root not in cwd.parents:
            raise ValueError(f"cwd must be under {root}")

    async def _ensure_directory_available(self, cwd: Path) -> None:
        live = await self.registry.list_sessions(statuses={"starting", "live", "idle"})
        for session in live:
            if Path(session.cwd).resolve() == cwd:
                raise ValueError(f"directory already has a live session: {cwd}")


def _tmux_session_name(cli: str, cwd: Path, session_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", cwd.name).strip("-") or "root"
    return f"conductor-{cli}-{slug}-{session_id[:8]}"
