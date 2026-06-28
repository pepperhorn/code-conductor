from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when conductor configuration is invalid."""


@dataclass(frozen=True)
class TelegramConfig:
    control_bot_token: str
    allowed_chat_ids: frozenset[int]


@dataclass(frozen=True)
class ProjectConfig:
    root_env: str
    root: Path
    max_depth: int


@dataclass(frozen=True)
class ChannelsConfig:
    slot_count_env: str
    slot_count: int


@dataclass(frozen=True)
class DefaultsConfig:
    cli: str
    bypass_permissions: bool
    idle_warning_minutes: int
    idle_timeout_minutes: int


@dataclass(frozen=True)
class RemoteControlConfig:
    auto_enable: bool


@dataclass(frozen=True)
class SessionFooterConfig:
    enabled: bool
    template: str


@dataclass(frozen=True)
class TrustConfig:
    auto_confirm_project_trust: bool
    trusted_root_only: bool


@dataclass(frozen=True)
class BotSlotConfig:
    name: str
    token: str


@dataclass(frozen=True)
class AppConfig:
    path: Path
    telegram: TelegramConfig
    project: ProjectConfig
    channels: ChannelsConfig
    defaults: DefaultsConfig
    remote_control: RemoteControlConfig
    session_footer: SessionFooterConfig
    trust: TrustConfig
    bot_slots: tuple[BotSlotConfig, ...]


def load_config(
    path: Path | str = "config.toml",
    environ: dict[str, str] | None = None,
) -> AppConfig:
    config_path = Path(path)
    env = os.environ if environ is None else environ
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    _warn_if_insecure_permissions(config_path)

    telegram_data = _table(data, "telegram")
    project_data = _table(data, "project")
    channels_data = _table(data, "channels")
    defaults_data = _table(data, "defaults")
    remote_data = _table(data, "remote_control")
    footer_data = data.get("session_footer", {})
    if footer_data and not isinstance(footer_data, dict):
        raise ConfigError("[session_footer] must be a table")
    trust_data = data.get("trust", {})
    if trust_data and not isinstance(trust_data, dict):
        raise ConfigError("[trust] must be a table")
    slot_data = data.get("bot_slots", [])
    if not isinstance(slot_data, list):
        raise ConfigError("[[bot_slots]] must be an array of tables")

    root_env = _str(project_data, "root_env")
    root_value = env.get(root_env, "").strip()
    if not root_value:
        raise ConfigError(f"{root_env} must be set")
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"{root_env} must resolve to an existing directory: {root}")

    slot_count_env = _str(channels_data, "slot_count_env")
    slot_count_raw = env.get(slot_count_env, "5").strip() or "5"
    try:
        slot_count = int(slot_count_raw)
    except ValueError as exc:
        raise ConfigError(f"{slot_count_env} must be a positive integer") from exc
    if slot_count <= 0:
        raise ConfigError(f"{slot_count_env} must be a positive integer")

    bot_slots = tuple(_bot_slot(item, idx) for idx, item in enumerate(slot_data, start=1))
    if len(bot_slots) != slot_count:
        raise ConfigError(
            "configured bot slot count "
            f"({len(bot_slots)}) must match {slot_count_env} ({slot_count})"
        )
    names = [slot.name for slot in bot_slots]
    if len(names) != len(set(names)):
        raise ConfigError("bot slot names must be unique")

    allowed_chat_ids = frozenset(_int_list(telegram_data, "allowed_chat_ids"))
    if not allowed_chat_ids:
        raise ConfigError("telegram.allowed_chat_ids must not be empty")

    idle_warning = _positive_int(defaults_data, "idle_warning_minutes")
    idle_timeout = _positive_int(defaults_data, "idle_timeout_minutes")
    if idle_warning >= idle_timeout:
        raise ConfigError("idle_warning_minutes must be lower than idle_timeout_minutes")

    cli = _str(defaults_data, "cli")
    if cli not in {"claude", "codex"}:
        raise ConfigError("defaults.cli must be 'claude' or 'codex'")

    return AppConfig(
        path=config_path,
        telegram=TelegramConfig(
            control_bot_token=_str(telegram_data, "control_bot_token"),
            allowed_chat_ids=allowed_chat_ids,
        ),
        project=ProjectConfig(
            root_env=root_env,
            root=root,
            max_depth=_positive_int(project_data, "max_depth"),
        ),
        channels=ChannelsConfig(slot_count_env=slot_count_env, slot_count=slot_count),
        defaults=DefaultsConfig(
            cli=cli,
            bypass_permissions=_bool(defaults_data, "bypass_permissions"),
            idle_warning_minutes=idle_warning,
            idle_timeout_minutes=idle_timeout,
        ),
        remote_control=RemoteControlConfig(auto_enable=_bool(remote_data, "auto_enable")),
        session_footer=SessionFooterConfig(
            enabled=_optional_bool(footer_data, "enabled", True),
            template=_optional_str(
                footer_data,
                "template",
                "cli:{cli} model:{model} cwd:{cwd} ctx:{context_remaining} "
                "session:{session_id} limit:{context_limit} data:{data_plane} slot:{bot_slot}",
            ),
        ),
        trust=TrustConfig(
            auto_confirm_project_trust=_optional_bool(
                trust_data,
                "auto_confirm_project_trust",
                True,
            ),
            trusted_root_only=_optional_bool(trust_data, "trusted_root_only", True),
        ),
        bot_slots=bot_slots,
    )


def _warn_if_insecure_permissions(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(f"warning: {path} should be chmod 600", flush=True)


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] table is required")
    return value


def _str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string")
    return value.strip()


def _bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be a boolean")
    return value


def _optional_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be a boolean")
    return value


def _optional_str(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    return value


def _positive_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{key} must be a positive integer")
    return value


def _int_list(data: dict[str, Any], key: str) -> list[int]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, int) for item in value):
        raise ConfigError(f"{key} must be a list of integers")
    return value


def _bot_slot(data: Any, idx: int) -> BotSlotConfig:
    if not isinstance(data, dict):
        raise ConfigError(f"bot slot #{idx} must be a table")
    return BotSlotConfig(name=_str(data, "name"), token=_str(data, "token"))
