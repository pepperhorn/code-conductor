from __future__ import annotations

import json
from pathlib import Path

from conductor.sessions import manager


def test_telegram_slot_env_creates_per_slot_access_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    env = manager._telegram_slot_env("slot 1", "TOKEN", frozenset({7772239134}))

    assert env["TELEGRAM_BOT_TOKEN"] == "TOKEN"
    assert env["TELEGRAM_STATE_DIR"] == str(
        tmp_path / ".claude" / "channels" / "telegram-slot-1"
    )
    access = json.loads(
        (tmp_path / ".claude" / "channels" / "telegram-slot-1" / "access.json").read_text()
    )
    assert access["dmPolicy"] == "allowlist"
    assert access["allowFrom"] == ["7772239134"]
