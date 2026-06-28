from __future__ import annotations

import os
from pathlib import Path

import pytest

from conductor.config import ConfigError, load_config


def write_config(path: Path, slot_count: int = 5) -> None:
    slots = "\n".join(
        f'[[bot_slots]]\nname = "session-bot-{idx}"\ntoken = "TOKEN_{idx}"\n'
        for idx in range(1, slot_count + 1)
    )
    path.write_text(
        f"""
[telegram]
control_bot_token = "CONTROL"
allowed_chat_ids = [123]

[project]
root_env = "CONDUCTOR_PROJECT_ROOT"
max_depth = 2

[channels]
slot_count_env = "CONDUCTOR_CHANNEL_SLOTS"

[defaults]
cli = "claude"
bypass_permissions = true
idle_warning_minutes = 25
idle_timeout_minutes = 30

[remote_control]
auto_enable = true

{slots}
""",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def test_load_config_resolves_env_root_and_default_slots(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path)

    config = load_config(
        config_path,
        environ={"CONDUCTOR_PROJECT_ROOT": str(tmp_path)},
    )

    assert config.project.root == tmp_path.resolve()
    assert config.channels.slot_count == 5
    assert len(config.bot_slots) == 5


def test_load_config_rejects_missing_project_root(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path)

    with pytest.raises(ConfigError, match="CONDUCTOR_PROJECT_ROOT must be set"):
        load_config(config_path, environ={})


def test_load_config_rejects_invalid_slot_count(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path)

    with pytest.raises(ConfigError, match="positive integer"):
        load_config(
            config_path,
            environ={"CONDUCTOR_PROJECT_ROOT": str(tmp_path), "CONDUCTOR_CHANNEL_SLOTS": "nope"},
        )


def test_load_config_rejects_slot_count_mismatch(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, slot_count=2)

    with pytest.raises(ConfigError, match="must match"):
        load_config(
            config_path,
            environ={"CONDUCTOR_PROJECT_ROOT": str(tmp_path), "CONDUCTOR_CHANNEL_SLOTS": "5"},
        )
