from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.storage.models import Slot, Booking

class SlotService:
    @staticmethod
    async def list_free(session: AsyncSession) -> list[Slot]:
        q = (
            select(Slot)
            .where(Slot.is_active == True)  # noqa
            .where(Slot.booking == None)    # noqa
            .order_by(Slot.start_at)
        )
        res = await session.execute(q)
        return list(res.scalars().all())

    @staticmethod
    async def list_all(session: AsyncSession) -> list[Slot]:
        res = await session.execute(select(Slot).order_by(Slot.start_at))
        return list(res.scalars().all())

    @staticmethod
    async def add_slot(session: AsyncSession, start_at: datetime) -> Slot:
        slot = Slot(start_at=start_at, is_active=True)
        session.add(slot)
        await session.commit()
        await session.refresh(slot)
        return slot

    @staticmethod
    async def activate(session: AsyncSession, slot_id: int, active: bool) -> None:
        slot = await session.get(Slot, slot_id)
        if not slot:
            return
        slot.is_active = active
        await session.commit()