from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def file_activity_iso(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).replace(microsecond=0).isoformat()
