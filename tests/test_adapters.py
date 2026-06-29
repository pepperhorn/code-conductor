from __future__ import annotations

import os
from pathlib import Path

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


def test_claude_builds_telegram_channel_command(tmp_path: Path) -> None:
    cmd = ClaudeCodeAdapter().build_launch_cmd(
        tmp_path,
        bypass=True,
        data_plane="telegram",
        bot_token="TOKEN",
    )

    assert cmd == [
        "claude",
        "--channels",
        "plugin:telegram@claude-plugins-official",
        "--permission-mode",
        "bypassPermissions",
    ]


def test_transcript_path_prefers_cwd_project_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cwd = Path("/home/shaun/conductor")
    sid = "abc123"
    projects = tmp_path / ".claude" / "projects"
    # Same session id under two project dirs; only one matches cwd.
    matching = projects / "-home-shaun-conductor"
    other = projects / "-home-shaun-other"
    for d in (other, matching):
        d.mkdir(parents=True)
        (d / f"{sid}.jsonl").write_text("{}\n", encoding="utf-8")

    result = ClaudeCodeAdapter().transcript_path(cwd, sid)

    assert result == matching / f"{sid}.jsonl"


def test_transcript_path_falls_back_to_newest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cwd = Path("/home/shaun/conductor")
    sid = "abc123"
    projects = tmp_path / ".claude" / "projects"
    older = projects / "-home-shaun-aaa"
    newer = projects / "-home-shaun-bbb"
    for d in (older, newer):
        d.mkdir(parents=True)
        (d / f"{sid}.jsonl").write_text("{}\n", encoding="utf-8")

    os.utime(older / f"{sid}.jsonl", (1000, 1000))
    os.utime(newer / f"{sid}.jsonl", (2000, 2000))

    result = ClaudeCodeAdapter().transcript_path(cwd, sid)

    assert result == newer / f"{sid}.jsonl"


def test_remote_control_capability_contract() -> None:
    # SessionManager.start degrades data planes off this capability instead of
    # hardcoding CLI names, so the contract must hold.
    assert ClaudeCodeAdapter().supports_remote_control() is True
    assert CodexAdapter().supports_remote_control() is False


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
