from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.storage.models import Booking, Slot, User
from typing import Optional

class BookingService:
    @staticmethod
    async def ensure_user(session: AsyncSession, tg_id: int, name: str | None) -> User:
        res = await session.execute(select(User).where(User.tg_id == tg_id))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg_id, name=name or "")
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    @staticmethod
    async def book(session: AsyncSession, user: User, slot_id: int, student_name: str, contact: str) -> Optional[Booking]:
        slot = await session.get(Slot, slot_id)
        if slot is None or slot.booking is not None or not slot.is_active:
            return None
        booking = Booking(user_id=user.id, slot_id=slot.id, student_name=student_name, student_contact=contact)
        session.add(booking)
        await session.commit()
        await session.refresh(booking)
        return booking

    @staticmethod
    async def my_bookings(session: AsyncSession, user: User) -> list[Booking]:
        res = await session.execute(select(Booking).where(Booking.user_id == user.id).order_by(Booking.id.desc()))
        return list(res.scalars().all())

    @staticmethod
    async def cancel(session: AsyncSession, booking_id: int, user: User) -> bool:
        booking = await session.get(Booking, booking_id)
        if booking is None or booking.user_id != user.id:
            return False
        await session.delete(booking)
        await session.commit()
        return True

    @staticmethod
    async def reschedule(session: AsyncSession, booking_id: int, user: User, new_slot_id: int) -> Optional[Booking]:
        booking = await session.get(Booking, booking_id)
        new_slot = await session.get(Slot, new_slot_id)
        if booking is None or booking.user_id != user.id or new_slot is None or new_slot.booking is not None:
            return None
        # освободить старый слот (просто переносим ссылку)
        booking.slot_id = new_slot.id
        await session.commit()
        await session.refresh(booking)
        return booking