from __future__ import annotations

import asyncio
import json
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
        launch_env: dict[str, str] = {}
        degraded_reason = None
        effective_data_plane = data_plane

        if not adapter.supports_remote_control() and data_plane in {"app", "both"}:
            effective_data_plane = "telegram" if data_plane == "both" else "tmux"
            degraded_reason = f"{cli} app data plane is unsupported; using telegram/tmux."

        if data_plane in {"telegram", "both"} or effective_data_plane == "telegram":
            slot = await self.bot_pool.lease(session_id)
            if slot is None:
                effective_data_plane = "app" if adapter.supports_remote_control() else "tmux"
                degraded_reason = "No Telegram slots free; started without a slot."
            else:
                bot_slot_name = slot.name
                bot_token = slot.token
                if cli == "claude":
                    launch_env.update(
                        _telegram_slot_env(
                            slot.name,
                            slot.token,
                            self.config.telegram.allowed_chat_ids,
                        )
                    )

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
                launch_env = {}
            effective_data_plane = "app" if adapter.supports_remote_control() else "tmux"
            degraded_reason = str(exc)
            argv = adapter.build_launch_cmd(
                cwd,
                bypass=bypass,
                data_plane=effective_data_plane,
                bot_token=None,
            )

        target = TmuxTarget(session=_tmux_session_name(cli, cwd, session_id))
        await self.tmux.start(target, str(cwd), argv, env=launch_env)
        await self._auto_confirm_trust_prompt(target.value, cwd)
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

    async def _auto_confirm_trust_prompt(self, target: str, cwd: Path) -> None:
        if not self.config.trust.auto_confirm_project_trust:
            return
        if self.config.trust.trusted_root_only:
            self._validate_cwd(cwd)
        for _ in range(10):
            await asyncio.sleep(0.5)
            pane = await self.tmux.capture(target)
            if _is_trust_prompt(pane):
                await self.tmux.send_enter(target)
                return

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


def _is_trust_prompt(pane: str) -> bool:
    prompts = (
        "Yes, I trust this folder",
        "Do you trust the contents of this directory?",
        "Is this a project you created or one you trust?",
    )
    return any(prompt in pane for prompt in prompts)


def _telegram_slot_env(
    slot_name: str,
    token: str,
    allowed_chat_ids: frozenset[int],
) -> dict[str, str]:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", slot_name).strip("-") or "slot"
    state_dir = Path.home() / ".claude" / "channels" / f"telegram-{safe_name}"
    state_dir.mkdir(parents=True, exist_ok=True)
    access_path = state_dir / "access.json"
    if not access_path.exists():
        access_path.write_text(
            json.dumps(
                {
                    "dmPolicy": "allowlist",
                    "allowFrom": [str(chat_id) for chat_id in sorted(allowed_chat_ids)],
                    "groups": {},
                    "pending": {},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        access_path.chmod(0o600)
    return {
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_STATE_DIR": str(state_dir),
    }
