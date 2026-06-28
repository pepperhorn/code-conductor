from __future__ import annotations

from dataclasses import dataclass
from string import Formatter

from conductor.config import SessionFooterConfig
from conductor.sessions.registry import SessionRecord

UNKNOWN = "unknown"


@dataclass(frozen=True)
class SessionStats:
    model: str = UNKNOWN
    context_remaining: str = UNKNOWN
    context_limit: str = UNKNOWN
    context_used: str = UNKNOWN


def render_session_footer(
    config: SessionFooterConfig,
    session: SessionRecord,
    stats: SessionStats | None = None,
) -> str:
    if not config.enabled:
        return ""
    stats = stats or SessionStats()
    values = {
        "cli": session.cli,
        "model": stats.model,
        "cwd": session.cwd,
        "context_remaining": stats.context_remaining,
        "session_id": session.id[:8],
        "context_limit": stats.context_limit,
        "context_used": stats.context_used,
        "data_plane": session.data_plane,
        "bot_slot": session.bot_slot or "-",
    }
    rendered = _safe_format(config.template, values)
    return f"\n\n{rendered}" if rendered else ""


def _safe_format(template: str, values: dict[str, str]) -> str:
    output = []
    formatter = Formatter()
    for literal, field_name, format_spec, conversion in formatter.parse(template):
        output.append(literal)
        if field_name is None:
            continue
        value = values.get(field_name, UNKNOWN)
        if conversion:
            value = format(value, f"!{conversion}")
        if format_spec:
            value = format(value, format_spec)
        output.append(value)
    return "".join(output)
