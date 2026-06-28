from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conductor.adapters.base import CLIAdapter, ResumableSession, UnsupportedDataPlane, Usage


class ClaudeCodeAdapter(CLIAdapter):
    name = "claude"

    def build_launch_cmd(
        self,
        cwd: Path,
        *,
        bypass: bool,
        data_plane: str,
        bot_token: str | None,
    ) -> list[str]:
        cmd = ["claude"]
        if data_plane in {"app", "both"}:
            cmd += ["--remote-control", cwd.name]
        if data_plane in {"telegram", "both"}:
            if not bot_token:
                raise UnsupportedDataPlane("telegram data plane requires a leased bot token")
            raise UnsupportedDataPlane(
                "Claude Telegram per-process token injection is not verified"
            )
        if bypass:
            cmd += ["--permission-mode", "bypassPermissions"]
        return cmd

    def build_resume_cmd(
        self,
        session_id: str,
        cwd: Path,
        *,
        bypass: bool,
        data_plane: str,
        bot_token: str | None,
    ) -> list[str]:
        cmd = ["claude", "--resume", session_id]
        if data_plane in {"app", "both"}:
            cmd += ["--remote-control", cwd.name]
        if data_plane in {"telegram", "both"}:
            if not bot_token:
                raise UnsupportedDataPlane("telegram data plane requires a leased bot token")
            raise UnsupportedDataPlane(
                "Claude Telegram per-process token injection is not verified"
            )
        if bypass:
            cmd += ["--permission-mode", "bypassPermissions"]
        return cmd

    def list_resumable(self, cwd: Path) -> list[ResumableSession]:
        # Claude exposes an interactive resume picker, but no stable non-interactive listing yet.
        return []

    def transcript_path(self, cwd: Path, session_id: str) -> Path | None:
        base = Path.home() / ".claude" / "projects"
        if not base.exists():
            return None
        candidates = list(base.glob(f"**/{session_id}.jsonl"))
        if candidates:
            return candidates[0]
        return None

    def parse_usage(self, transcript_path: Path) -> Usage | None:
        if not transcript_path.exists():
            return None
        latest: Usage | None = None
        for line in transcript_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = _extract_usage(event)
            if usage:
                latest = usage
        return latest

    def supports_remote_control(self) -> bool:
        return True

    def settings_bypass_patch(self, cwd: Path) -> None:
        settings_dir = cwd / ".claude"
        settings_dir.mkdir(exist_ok=True)
        settings_path = settings_dir / "settings.local.json"
        data: dict[str, Any] = {}
        if settings_path.exists():
            try:
                loaded = json.loads(settings_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except json.JSONDecodeError:
                data = {}
        data.setdefault("permissions", {})
        permissions = data["permissions"]
        if isinstance(permissions, dict):
            permissions["allow"] = ["*"]
        settings_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _extract_usage(event: dict[str, Any]) -> Usage | None:
    message = event.get("message")
    usage = None
    if isinstance(message, dict):
        usage = message.get("usage")
    if usage is None:
        usage = event.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = _int_value(usage, "input_tokens")
    output_tokens = _int_value(usage, "output_tokens")
    cache_read = _int_value(usage, "cache_read_input_tokens")
    cache_create = _int_value(usage, "cache_creation_input_tokens")
    limit = _int_value(usage, "context_window") or _int_value(usage, "limit")
    used = input_tokens + output_tokens + cache_read + cache_create
    if used <= 0 or limit <= 0:
        return None
    return Usage(used=used, limit=limit)


def _int_value(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    return value if isinstance(value, int) else 0
