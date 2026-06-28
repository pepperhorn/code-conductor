from __future__ import annotations

from pathlib import Path

import pytest

from conductor.adapters.base import UnsupportedDataPlane
from conductor.adapters.claude_code import ClaudeCodeAdapter
from conductor.adapters.codex import CodexAdapter


def test_claude_builds_remote_control_command(tmp_path: Path) -> None:
    cmd = ClaudeCodeAdapter().build_launch_cmd(
        tmp_path,
        bypass=True,
        data_plane="app",
        bot_token=None,
    )

    assert cmd == [
        "claude",
        "--remote-control",
        tmp_path.name,
        "--permission-mode",
        "bypassPermissions",
    ]


def test_claude_rejects_unverified_telegram_injection(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedDataPlane):
        ClaudeCodeAdapter().build_launch_cmd(
            tmp_path,
            bypass=True,
            data_plane="telegram",
            bot_token="TOKEN",
        )


def test_codex_degrades_to_tmux_style_command(tmp_path: Path) -> None:
    cmd = CodexAdapter().build_launch_cmd(
        tmp_path,
        bypass=True,
        data_plane="tmux",
        bot_token=None,
    )

    assert cmd == [
        "codex",
        "--cd",
        str(tmp_path),
        "--no-alt-screen",
        "--dangerously-bypass-approvals-and-sandbox",
    ]
