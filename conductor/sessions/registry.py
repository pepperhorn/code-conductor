from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from conductor.config import BotSlotConfig


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class SessionRecord:
    id: str
    cli: str
    cwd: str
    tmux_target: str
    data_plane: str
    bot_slot: str | None
    status: str
    started_at: str
    last_activity: str | None
    fired_thresholds: tuple[int, ...]


@dataclass(frozen=True)
class BotSlotRecord:
    name: str
    token: str
    leased_session_id: str | None


class Registry:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)

    async def init(self, slots: tuple[BotSlotConfig, ...]) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  cli TEXT NOT NULL,
                  cwd TEXT NOT NULL,
                  tmux_target TEXT NOT NULL,
                  data_plane TEXT NOT NULL,
                  bot_slot TEXT,
                  status TEXT NOT NULL,
                  started_at TEXT NOT NULL,
                  last_activity TEXT,
                  fired_thresholds TEXT DEFAULT '[]'
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_slots (
                  name TEXT PRIMARY KEY,
                  token TEXT NOT NULL,
                  leased_session_id TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS audit (
                  ts TEXT,
                  chat_id INTEGER,
                  command TEXT,
                  detail TEXT
                )
                """
            )
            for slot in slots:
                await db.execute(
                    """
                    INSERT INTO bot_slots(name, token, leased_session_id)
                    VALUES (?, ?, NULL)
                    ON CONFLICT(name) DO UPDATE SET token = excluded.token
                    """,
                    (slot.name, slot.token),
                )
            configured = {slot.name for slot in slots}
            if configured:
                placeholders = ",".join("?" for _ in configured)
                await db.execute(
                    f"DELETE FROM bot_slots WHERE name NOT IN ({placeholders})",  # noqa: S608
                    tuple(configured),
                )
            await db.commit()

    async def create_session(self, record: SessionRecord) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions(
                  id, cli, cwd, tmux_target, data_plane, bot_slot, status,
                  started_at, last_activity, fired_thresholds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.cli,
                    record.cwd,
                    record.tmux_target,
                    record.data_plane,
                    record.bot_slot,
                    record.status,
                    record.started_at,
                    record.last_activity,
                    json.dumps(list(record.fired_thresholds)),
                ),
            )
            await db.commit()

    async def list_sessions(self, statuses: set[str] | None = None) -> list[SessionRecord]:
        query = "SELECT * FROM sessions"
        params: tuple[str, ...] = ()
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"  # noqa: S608
            params = tuple(statuses)
        query += " ORDER BY started_at DESC"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(query, params)
        return [_session_from_row(row) for row in rows]

    async def get_session(self, session_id: str) -> SessionRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return _session_from_row(rows[0]) if rows else None

    async def update_session_status(
        self,
        session_id: str,
        status: str,
        *,
        last_activity: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            if last_activity is None:
                await db.execute(
                    "UPDATE sessions SET status = ? WHERE id = ?",
                    (status, session_id),
                )
            else:
                await db.execute(
                    "UPDATE sessions SET status = ?, last_activity = ? WHERE id = ?",
                    (status, last_activity, session_id),
                )
            await db.commit()

    async def set_fired_thresholds(self, session_id: str, thresholds: tuple[int, ...]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sessions SET fired_thresholds = ? WHERE id = ?",
                (json.dumps(list(thresholds)), session_id),
            )
            await db.commit()

    async def list_slots(self) -> list[BotSlotRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall("SELECT * FROM bot_slots ORDER BY name")
        return [BotSlotRecord(**dict(row)) for row in rows]

    async def lease_slot(self, session_id: str) -> BotSlotRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            rows = await db.execute_fetchall(
                "SELECT * FROM bot_slots WHERE leased_session_id IS NULL ORDER BY name LIMIT 1"
            )
            if not rows:
                await db.rollback()
                return None
            row = rows[0]
            await db.execute(
                "UPDATE bot_slots SET leased_session_id = ? WHERE name = ?",
                (session_id, row["name"]),
            )
            await db.commit()
            return BotSlotRecord(
                name=row["name"],
                token=row["token"],
                leased_session_id=session_id,
            )

    async def release_slot(self, name: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE bot_slots SET leased_session_id = NULL WHERE name = ?",
                (name,),
            )
            await db.execute("UPDATE sessions SET bot_slot = NULL WHERE bot_slot = ?", (name,))
            await db.commit()

    async def release_session_slot(self, session_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE bot_slots SET leased_session_id = NULL WHERE leased_session_id = ?",
                (session_id,),
            )
            await db.commit()

    async def audit(self, chat_id: int, command: str, detail: str = "") -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO audit(ts, chat_id, command, detail) VALUES (?, ?, ?, ?)",
                (utc_now_iso(), chat_id, command, detail),
            )
            await db.commit()


def _session_from_row(row: aiosqlite.Row) -> SessionRecord:
    thresholds = json.loads(row["fired_thresholds"] or "[]")
    return SessionRecord(
        id=row["id"],
        cli=row["cli"],
        cwd=row["cwd"],
        tmux_target=row["tmux_target"],
        data_plane=row["data_plane"],
        bot_slot=row["bot_slot"],
        status=row["status"],
        started_at=row["started_at"],
        last_activity=row["last_activity"],
        fired_thresholds=tuple(int(item) for item in thresholds),
    )
