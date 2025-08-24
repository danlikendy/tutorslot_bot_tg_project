from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from zoneinfo import ZoneInfo

from app.config import settings
from app.storage.models import Booking, WeeklySubscription
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

        # Проверяем что занятие еще не прошло
        if start_at <= now:
            log.info("reminders.skip booking=%s - lesson already passed: %s <= %s",
                     booking.id, start_at, now)
            return

        for minutes in settings.remind_offsets_minutes:
            minutes = int(minutes)
            when = start_at - timedelta(minutes=minutes)
            
            # Проверяем что время напоминания еще не прошло
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
            except Exception as e:
                log.error(f"Failed to send reminder to user {booking.user.tg_id}: {e}")

            for admin_id in settings.admins:
                try:
                    await bot.send_message(
                        admin_id,
                        f"Напоминание (ученик): {student}\nКогда: {when_txt}\nКонтакт: {booking.student_contact or '—'}",
                    )
                except Exception as e:
                    log.error(f"Failed to send reminder to admin {admin_id}: {e}")

            if EmailService.is_email(booking.student_contact):
                try:
                    EmailService.send(
                        to_email=booking.student_contact,
                        subject="Напоминание о занятии",
                        body=f"Здравствуйте!\nНапоминаем о занятии: {when_txt}\nУченик: {student}",
                    )
                except Exception as e:
                    log.error(f"Failed to send email reminder to {booking.student_contact}: {e}")

            log.info("reminders.fire booking=%s -> sent", booking_id)

    @staticmethod
    async def schedule_for_weekly(scheduler, sub: WeeklySubscription, tz_name: str = settings.tz):
        if not settings.reminders_enabled or scheduler is None or sub is None or not sub.is_active:
            return

        try:
            hh, mm = map(int, sub.time_hhmm.split(":"))
        except Exception:
            log.warning("weekly.schedule: bad time_hhmm=%s for sub=%s", sub.time_hhmm, sub.id)
            return

        dow_24 = (sub.weekday - 1) % 7

        if hh == 0:
            dow_1 = (sub.weekday - 1) % 7
            hh_1 = 23
            mm_1 = mm
        else:
            dow_1 = sub.weekday
            hh_1 = hh - 1
            mm_1 = mm

        job_id_24 = f"weekly_sub_{sub.id}_d24"
        try:
            scheduler.remove_job(job_id_24)
        except Exception:
            pass
        scheduler.add_job(
            ReminderService.send_weekly_subscription_reminder_job,
            trigger="cron",
            day_of_week=dow_24, hour=hh, minute=mm,
            id=job_id_24,
            kwargs={"sub_id": sub.id, "offset_min": 1440, "tz_name": tz_name},
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=60,
        )

        job_id_1 = f"weekly_sub_{sub.id}_d1"
        try:
            scheduler.remove_job(job_id_1)
        except Exception:
            pass
        scheduler.add_job(
            ReminderService.send_weekly_subscription_reminder_job,
            trigger="cron",
            day_of_week=dow_1, hour=hh_1, minute=mm_1,
            id=job_id_1,
            kwargs={"sub_id": sub.id, "offset_min": 60, "tz_name": tz_name},
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=60,
        )

        log.info("reminders.schedule weekly sub=%s -> d24@dow=%s %02d:%02d, d1@dow=%s %02d:%02d",
                 sub.id, dow_24, hh, mm, dow_1, hh_1, mm_1)

    @staticmethod
    async def cancel_for_weekly(scheduler, sub_id: int):
        if not settings.reminders_enabled or scheduler is None:
            return
        for suffix in ("d24", "d1"):
            job_id = f"weekly_sub_{sub_id}_{suffix}"
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
        log.info("reminders.cancel weekly sub=%s", sub_id)

    @staticmethod
    async def send_weekly_subscription_reminder_job(sub_id: int, offset_min: int, tz_name: str):
        from sqlalchemy import select
        from app.storage.db import SessionLocal
        from app.storage.models import WeeklySubscription as WS, User as U
        from app.runtime import get_bot

        async with SessionLocal() as session:
            res = await session.execute(select(WS).where(WS.id == sub_id))
            sub: Optional[WS] = res.scalar_one_or_none()
            if not sub or not sub.is_active:
                log.info("reminders.weekly.fire sub=%s -> not found or inactive", sub_id)
                return

            tz = ZoneInfo(tz_name)
            now = datetime.now(tz)
            hh, mm = map(int, sub.time_hhmm.split(":"))
            days_ahead = (sub.weekday - now.weekday()) % 7
            start_at = (now + timedelta(days=days_ahead)).replace(
                hour=hh, minute=mm, second=0, microsecond=0
            )

            student = sub.student_name or "Ученик"
            when_txt = format_dt_ru(start_at)

            bot: Bot = get_bot()

            ures = await session.execute(select(U).where(U.id == sub.user_id))
            user = ures.scalar_one_or_none()

            try:
                if user and user.tg_id:
                    await bot.send_message(
                        user.tg_id, f"Напоминание о еженедельном занятии\n{when_txt}\nИмя: {student}"
                    )
            except Exception as e:
                log.error(f"Failed to send weekly reminder to user {user.tg_id}: {e}")

            for admin_id in settings.admins:
                try:
                    await bot.send_message(
                        admin_id,
                        f"Еженедельное напоминание (ученик): {student}\nКогда: {when_txt}\nКонтакт: {sub.student_contact or '—'}",
                    )
                except Exception as e:
                    log.error(f"Failed to send weekly reminder to admin {admin_id}: {e}")

            email = sub.student_contact or ""
            if EmailService.is_email(email):
                try:
                    EmailService.send(
                        to_email=email,
                        subject="Напоминание о занятии (еженедельно)",
                        body=f"Здравствуйте!\nНапоминаем о занятии: {when_txt}\nУченик: {student}",
                    )
                except Exception as e:
                    log.error(f"Failed to send weekly email reminder to {email}: {e}")

            log.info("reminders.weekly.fire sub=%s offset=%s -> sent", sub_id, offset_min)