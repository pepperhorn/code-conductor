from __future__ import annotations

from pathlib import Path

from conductor.adapters.claude_code import ClaudeCodeAdapter


def test_settings_bypass_patch_does_not_write_invalid_wildcard(tmp_path: Path) -> None:
    ClaudeCodeAdapter().settings_bypass_patch(tmp_path)

    assert not (tmp_path / ".claude" / "settings.local.json").exists()
