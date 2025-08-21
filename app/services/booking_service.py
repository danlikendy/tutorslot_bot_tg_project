from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.storage.models import Booking, Slot, User
from app.services.reminder_service import ReminderService
from app.services.google_calendar_service import GoogleCalendarService


def _get_scheduler_safe():
    try:
        from app.main import get_scheduler  # импорт только в момент вызова
        return get_scheduler()
    except Exception:
        return None


class BookingService:
    @staticmethod
    async def ensure_user(session, tg_id: int, full_name: str) -> User:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))
        normalized_name = (full_name or "").strip()
        if user is None:
            user = User(tg_id=tg_id, name=normalized_name)
            session.add(user)
            await session.flush()
        else:
            if (user.name or "") != normalized_name:
                user.name = normalized_name
                await session.flush()
        return user

    @staticmethod
    async def book_at(
        session,
        user: User,
        start_at: datetime,
        student_name: str,
        contact: Optional[str] = None,
    ) -> Optional[Booking]:
        
        booked_id = await session.scalar(
            select(Booking.id)
            .join(Slot, Slot.id == Booking.slot_id)
            .where(Slot.start_at == start_at)
            .limit(1)
        )
        if booked_id is not None:
            return None

        slot_id = await session.scalar(
            select(Slot.id).where(Slot.start_at == start_at).limit(1)
        )
        if slot_id is None:
            new_slot = Slot(start_at=start_at)
            session.add(new_slot)
            await session.flush()
            slot_id = new_slot.id

        booking = Booking(
            user_id=user.id,
            slot_id=slot_id,
            student_name=student_name,
            student_contact=(contact or None),
        )
        session.add(booking)
        await session.flush()
        await session.commit()

        booked = await session.scalar(
            select(Booking)
            .options(selectinload(Booking.slot))
            .where(Booking.id == booking.id)
        )

        try:
            if settings.google_calendar_enabled and booked:
                ev_id = GoogleCalendarService.create_event(
                    booked.id,
                    booked.slot.start_at,
                    booked.student_name,
                    booked.student_contact,
                )
                if ev_id:
                    booked.gcal_event_id = ev_id
                    await session.commit()
        except Exception:
            pass

        try:
            if booked:
                sched = _get_scheduler_safe()
                if sched:
                    await ReminderService.schedule_for_booking(sched, booked)
        except Exception:
            pass

        return booked

    @staticmethod
    async def my_bookings(session, user: User) -> List[Booking]:
        res = await session.execute(
            select(Booking)
            .options(selectinload(Booking.slot))
            .where(Booking.user_id == user.id)
            .order_by(Booking.id.desc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def admin_cancel(session, booking_id: int) -> bool:
        booking = await session.scalar(
            select(Booking)
            .options(selectinload(Booking.slot))
            .where(Booking.id == booking_id)
        )
        if booking is None:
            return False

        try:
            if settings.google_calendar_enabled and booking.gcal_event_id:
                GoogleCalendarService.delete_event(booking.gcal_event_id)
        except Exception:
            pass

        try:
            sched = _get_scheduler_safe()
            if sched:
                await ReminderService.cancel_for_booking(sched, booking_id)
        except Exception:
            pass

        await session.delete(booking)
        await session.commit()
        return True

    @staticmethod
    async def reschedule_to(session, booking_id: int, new_start_at: datetime) -> bool:
        booking = await session.scalar(
            select(Booking)
            .options(selectinload(Booking.slot))
            .where(Booking.id == booking_id)
        )
        if booking is None:
            return False

        new_slot = await session.scalar(
            select(Slot).where(Slot.start_at == new_start_at).limit(1)
        )
        if new_slot is None:
            new_slot = Slot(start_at=new_start_at)
            session.add(new_slot)
            await session.flush()

        taken_id = await session.scalar(
            select(Booking.id).where(Booking.slot_id == new_slot.id).limit(1)
        )
        if taken_id is not None:
            return False

        booking.slot_id = new_slot.id
        await session.flush()
        await session.commit()

        booked = await session.scalar(
            select(Booking)
            .options(selectinload(Booking.slot))
            .where(Booking.id == booking_id)
        )

        if booked:
            try:
                if settings.google_calendar_enabled and booked.gcal_event_id:
                    GoogleCalendarService.update_event(
                        booked.gcal_event_id,
                        booked.slot.start_at,
                        booked.student_name,
                        booked.student_contact,
                    )
            except Exception:
                pass

            try:
                sched = _get_scheduler_safe()
                if sched:
                    await ReminderService.cancel_for_booking(sched, booking_id)
                    await ReminderService.schedule_for_booking(sched, booked)
            except Exception:
                pass

        return True

    @staticmethod
    async def admin_update_content(
        session,
        booking_id: int,
        student_name: Optional[str] = None,
        contact: Optional[str] = None,
    ) -> bool:

        booking = await session.scalar(
            select(Booking)
            .options(selectinload(Booking.slot))
            .where(Booking.id == booking_id)
        )
        if booking is None:
            return False

        changed = False
        if student_name is not None and booking.student_name != student_name:
            booking.student_name = student_name
            changed = True
        if contact is not None and booking.student_contact != contact:
            booking.student_contact = contact
            changed = True

        if changed:
            await session.commit()
            try:
                if settings.google_calendar_enabled and booking.gcal_event_id:
                    GoogleCalendarService.update_event(
                        booking.gcal_event_id,
                        booking.slot.start_at,
                        booking.student_name,
                        booking.student_contact,
                    )
            except Exception:
                pass
        return True