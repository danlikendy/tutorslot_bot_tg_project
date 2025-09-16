from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.storage.models import Booking
from app.services.reminder_service import ReminderService
from app.services.google_calendar_service import GoogleCalendarService
from app.services.email_service import EmailService
from app.utils.dates import format_dt_ru

log = logging.getLogger("reminders.setup")
TZ = ZoneInfo(settings.tz)

def setup_scheduler(scheduler, SessionLocal, bot) -> None:
    async def rebuild() -> None:
        try:
            async with SessionLocal() as session:
                res = await session.execute(
                    select(Booking).options(selectinload(Booking.slot))
                )
                bookings = list(res.scalars().all())

            for b in bookings:
                await ReminderService.schedule_for_booking(scheduler, b)

            log.info("reminders.rebuild done: %s bookings", len(bookings))
        except Exception:
            log.exception("reminders.rebuild failed")

    run_at = datetime.now(TZ) + timedelta(seconds=1)
    scheduler.add_job(
        rebuild,
        trigger="date",
        run_date=run_at,
        id="reminders.rebuild",
        replace_existing=True,
    )
    log.info("reminders.rebuild scheduled at %s", run_at)


async def schedule_interval_event_creation(booking_id: int, next_start_at: datetime):
    """Планирует создание следующего события для интервального занятия"""
    try:
        from app.main import get_scheduler
        scheduler = get_scheduler()
        if not scheduler:
            log.error("Scheduler not available for interval event creation")
            return
        
        # Планируем создание события за день до занятия (в воскресенье)
        notification_time = next_start_at - timedelta(days=1)
        notification_time = notification_time.replace(hour=12, minute=0, second=0, microsecond=0)
        
        # Если время уже прошло, планируем на следующее воскресенье
        now = datetime.now(TZ)
        if notification_time <= now:
            notification_time += timedelta(days=7)
        
        job_id = f"interval_event_{booking_id}_{next_start_at.strftime('%Y%m%d')}"
        
        scheduler.add_job(
            create_next_interval_event,
            trigger="date",
            run_date=notification_time,
            args=[booking_id, next_start_at],
            id=job_id,
            replace_existing=True,
        )
        
        log.info(f"Scheduled interval event creation for booking {booking_id} at {notification_time}")
        
    except Exception as e:
        log.error(f"Failed to schedule interval event creation for booking {booking_id}: {e}")


async def create_next_interval_event(booking_id: int, start_at: datetime):
    """Создает следующее событие для интервального занятия и отправляет уведомление"""
    try:
        from app.storage.db import SessionLocal
        
        async with SessionLocal() as session:
            # Получаем запись
            booking = await session.scalar(
                select(Booking).where(Booking.id == booking_id)
            )
            
            if not booking or booking.lesson_type != "interval":
                log.warning(f"Interval booking {booking_id} not found or not interval type")
                return
            
            # Создаем событие в календаре
            if settings.google_calendar_enabled:
                weekday_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
                weekday_name = weekday_names[start_at.weekday()]
                
                # Создаем новый слот для следующего события
                from app.storage.models import Slot
                slot = Slot(start_at=start_at)
                session.add(slot)
                await session.flush()
                
                # Обновляем слот в записи
                booking.slot_id = slot.id
                
                ev_id = GoogleCalendarService.create_event(
                    booking.id,
                    start_at,
                    f"{booking.student_name} ({weekday_name})",
                    booking.student_contact,
                )
                
                if ev_id:
                    # Обновляем ID события в базе
                    booking.gcal_event_id = ev_id
                    await session.flush()
                    log.info(f"Created next interval event: {ev_id} for {start_at}")
                    
                    # Планируем следующее событие через неделю
                    from app.services.booking_service import _schedule_next_interval_event
                    await _schedule_next_interval_event(session, booking, start_at)
            
            # Отправляем уведомление на email
            if settings.smtp_enabled and EmailService.is_email(booking.student_contact):
                try:
                    when_txt = format_dt_ru(start_at.astimezone(TZ))
                    
                    success = EmailService.send(
                        to_email=booking.student_contact,
                        subject="Напоминание о занятии на следующей неделе",
                        body=f"Здравствуйте!\n\nНапоминаем о предстоящем занятии:\n"
                             f"Дата и время: {when_txt}\n"
                             f"Ученик: {booking.student_name}\n"
                             f"Контакт: {booking.student_contact}\n\n"
                             f"Запись #{booking.id}\n\n"
                             f"С уважением,\nРепетитор"
                    )
                    if success:
                        log.info(f"Sent weekly reminder email to {booking.student_contact} for booking {booking.id}")
                    else:
                        log.warning(f"Failed to send weekly reminder email to {booking.student_contact} for booking {booking.id}")
                except Exception as e:
                    log.error(f"Failed to send weekly reminder email to {booking.student_contact}: {e}")
            
            await session.commit()
            
    except Exception as e:
        log.error(f"Failed to create next interval event for booking {booking_id}: {e}")