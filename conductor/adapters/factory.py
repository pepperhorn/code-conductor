from __future__ import annotations

from conductor.adapters.base import CLIAdapter
from conductor.adapters.claude_code import ClaudeCodeAdapter
from conductor.adapters.codex import CodexAdapter


def get_adapter(name: str) -> CLIAdapter:
    if name == "claude":
        return ClaudeCodeAdapter()
    if name == "codex":
        return CodexAdapter()
    raise ValueError(f"unknown CLI adapter: {name}")
