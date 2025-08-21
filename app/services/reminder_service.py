from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from zoneinfo import ZoneInfo

from app.config import settings
from app.storage.models import Booking
from app.services.email_service import EmailService
from app.utils.dates import format_dt_ru

log = logging.getLogger("reminders")
TZ = ZoneInfo(settings.tz)

class ReminderService:
    @staticmethod
    async def schedule_for_booking(scheduler, booking: Booking):
        if not settings.reminders_enabled or scheduler is None or booking is None:
            return

        start_at: datetime = booking.slot.start_at
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=TZ)
        now = datetime.now(TZ)

        for minutes in settings.remind_offsets_minutes:
            minutes = int(minutes)
            when = start_at - timedelta(minutes=minutes)
            if when <= now:
                log.info("reminders.skip booking=%s offset=%s when=%s <= now=%s",
                         booking.id, minutes, when, now)
                continue

            job_id = f"remind:{booking.id}:{minutes}"
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass

            scheduler.add_job(
                ReminderService.send_reminder_job,
                trigger="date",
                run_date=when,
                id=job_id,
                kwargs={"booking_id": booking.id},
                misfire_grace_time=60,
                coalesce=True,
                replace_existing=True,
            )
            log.info("reminders.schedule booking=%s offset=%s run_at=%s",
                     booking.id, minutes, when)

    @staticmethod
    async def cancel_for_booking(scheduler, booking_id: int):
        if not settings.reminders_enabled or scheduler is None:
            return
        for minutes in settings.remind_offsets_minutes:
            job_id = f"remind:{booking_id}:{int(minutes)}"
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
        log.info("reminders.cancel booking=%s", booking_id)

    @staticmethod
    async def send_reminder_job(booking_id: int):
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.storage.db import SessionLocal
        from app.storage.models import Booking as B
        from app.runtime import get_bot

        async with SessionLocal() as session:
            res = await session.execute(
                select(B).options(selectinload(B.slot), selectinload(B.user)).where(B.id == booking_id)
            )
            booking: Optional[B] = res.scalar_one_or_none()
            if not booking:
                log.info("reminders.fire booking=%s -> not found", booking_id)
                return

            student = booking.student_name or "Ученик"
            dt = booking.slot.start_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            when_txt = format_dt_ru(dt)

            bot: Bot = get_bot()

            try:
                if booking.user and booking.user.tg_id:
                    await bot.send_message(
                        booking.user.tg_id, f"Напоминание о занятии\n{when_txt}\nИмя: {student}"
                    )
            except Exception:
                pass

            for admin_id in settings.admins:
                try:
                    await bot.send_message(
                        admin_id,
                        f"Напоминание (ученик): {student}\nКогда: {when_txt}\nКонтакт: {booking.student_contact or '—'}",
                    )
                except Exception:
                    pass

            if EmailService.is_email(booking.student_contact):
                EmailService.send(
                    to_email=booking.student_contact,
                    subject="Напоминание о занятии",
                    body=f"Здравствуйте!\nНапоминаем о занятии: {when_txt}\nУченик: {student}",
                )

            log.info("reminders.fire booking=%s -> sent", booking_id)