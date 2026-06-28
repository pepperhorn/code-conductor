from __future__ import annotations

from string import Formatter

from conductor.config import SessionFooterConfig
from conductor.sessions.registry import SessionRecord

UNKNOWN = "unknown"


def render_session_footer(config: SessionFooterConfig, session: SessionRecord) -> str:
    if not config.enabled:
        return ""
    values = {
        "cli": session.cli,
        "model": UNKNOWN,
        "cwd": session.cwd,
        "context_remaining": UNKNOWN,
        "session_id": session.id[:8],
        "context_limit": UNKNOWN,
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
