from __future__ import annotations

from pathlib import Path

from conductor.adapters.base import CLIAdapter, ResumableSession, Usage


class CodexAdapter(CLIAdapter):
    name = "codex"

    def build_launch_cmd(
        self,
        cwd: Path,
        *,
        bypass: bool,
        data_plane: str,
        bot_token: str | None,
    ) -> list[str]:
        cmd = ["codex", "--cd", str(cwd), "--no-alt-screen"]
        if bypass:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            cmd += ["--ask-for-approval", "on-request", "--sandbox", "workspace-write"]
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
        cmd = ["codex", "resume", "--cd", str(cwd), "--no-alt-screen"]
        if bypass:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            cmd += ["--ask-for-approval", "on-request", "--sandbox", "workspace-write"]
        cmd.append(session_id)
        return cmd

    def list_resumable(self, cwd: Path) -> list[ResumableSession]:
        return []

    def transcript_path(self, cwd: Path, session_id: str) -> Path | None:
        return None

    def parse_usage(self, transcript_path: Path) -> Usage | None:
        return None

    def supports_remote_control(self) -> bool:
        return False

    def settings_bypass_patch(self, cwd: Path) -> None:
        return None
