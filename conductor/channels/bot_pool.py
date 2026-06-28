from __future__ import annotations

from conductor.sessions.registry import BotSlotRecord, Registry


class BotPool:
    def __init__(self, registry: Registry):
        self.registry = registry

    async def list(self) -> list[BotSlotRecord]:
        return await self.registry.list_slots()

    async def lease(self, session_id: str) -> BotSlotRecord | None:
        return await self.registry.lease_slot(session_id)

    async def release(self, name: str) -> None:
        await self.registry.release_slot(name)

    async def release_for_session(self, session_id: str) -> None:
        await self.registry.release_session_slot(session_id)
