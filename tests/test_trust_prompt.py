from __future__ import annotations

from conductor.sessions.manager import _is_trust_prompt


def test_detects_codex_trust_prompt() -> None:
    assert _is_trust_prompt("Do you trust the contents of this directory?")


def test_detects_claude_trust_prompt() -> None:
    assert _is_trust_prompt("1. Yes, I trust this folder")


def test_ignores_regular_pane_text() -> None:
    assert not _is_trust_prompt("Claude Code v2.1.195\n/remote-control is active")
