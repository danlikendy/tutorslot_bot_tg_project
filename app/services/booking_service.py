from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.storage.models import Booking, Slot, User
from app.services.reminder_service import ReminderService
from app.services.google_calendar_service import GoogleCalendarService

log = logging.getLogger(__name__)


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
        lesson_type: str = "single",
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
            lesson_type=lesson_type,
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
                    log.info(f"Created Google Calendar event: {ev_id} for booking {booked.id}")
                else:
                    log.error(f"Failed to create Google Calendar event for booking {booked.id}")
        except Exception as e:
            log.error(f"Exception creating Google Calendar event for booking {booked.id}: {e}")

        try:
            if booked:
                sched = _get_scheduler_safe()
                if sched:
                    await ReminderService.schedule_for_booking(sched, booked)
                
                # Отправляем немедленное уведомление на email
                from app.services.email_service import EmailService
                if settings.smtp_enabled and EmailService.is_email(booked.student_contact):
                    try:
                        from app.utils.dates import format_dt_ru
                        from zoneinfo import ZoneInfo
                        
                        start_at = booked.slot.start_at
                        if start_at.tzinfo is None:
                            start_at = start_at.replace(tzinfo=ZoneInfo(settings.tz))
                        
                        when_txt = format_dt_ru(start_at.astimezone(ZoneInfo(settings.tz)))
                        
                        success = EmailService.send(
                            to_email=booked.student_contact,
                            subject="Подтверждение записи на занятие",
                            body=f"Здравствуйте!\n\nВы успешно записаны на занятие:\n"
                                 f"Дата и время: {when_txt}\n"
                                 f"Ученик: {booked.student_name}\n"
                                 f"Контакт: {booked.student_contact}\n\n"
                                 f"Запись #{booked.id}\n\n"
                                 f"С уважением,\nРепетитор"
                        )
                        if success:
                            log.info(f"Sent confirmation email to {booked.student_contact} for booking {booked.id}")
                        else:
                            log.warning(f"Failed to send confirmation email to {booked.student_contact} for booking {booked.id}")
                    except Exception as e:
                        log.error(f"Failed to send confirmation email to {booked.student_contact}: {e}")
                else:
                    log.info(f"Email disabled or invalid email address: {booked.student_contact}")
        except Exception as e:
            log.error(f"Exception scheduling reminders for booking {booked.id}: {e}")

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

        # Сохраняем ID события для удаления из календаря
        gcal_event_id = booking.gcal_event_id
        slot = booking.slot

        try:
            if settings.google_calendar_enabled and gcal_event_id:
                GoogleCalendarService.delete_event(gcal_event_id)
                log.info(f"Deleted Google Calendar event: {gcal_event_id}")
        except Exception as e:
            log.error(f"Failed to delete Google Calendar event: {e}")

        try:
            sched = _get_scheduler_safe()
            if sched:
                await ReminderService.cancel_for_booking(sched, booking_id)
        except Exception as e:
            log.error(f"Exception canceling reminders for booking {booking_id}: {e}")

        # Удаляем запись
        await session.delete(booking)
        
        # Если это одиночное занятие, удаляем и слот
        if booking.lesson_type == "single" and slot is not None:
            await session.delete(slot)
            log.info(f"Deleted slot {slot.id} for cancelled booking {booking_id}")
        
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
                    log.info(f"Force rescheduling event {booked.gcal_event_id} - recreating to ensure calendar update")
                    
                    # Используем принудительное обновление с пересозданием
                    # ВАЖНО: передаем НОВОЕ время (new_start_at), а не старое из базы
                    new_event_id = GoogleCalendarService.force_update_event(
                        booked.gcal_event_id,
                        new_start_at,  # Используем НОВОЕ время, а не booked.slot.start_at
                        booked.student_name,
                        booked.student_contact,
                        booked.id  # Передаем правильный booking_id
                    )
                    
                    if new_event_id:
                        log.info(f"Successfully force updated Google Calendar event for rescheduling")
                        # Обновляем ID события в базе данных
                        booked.gcal_event_id = new_event_id
                        await session.commit()
                        log.info(f"Updated booking with new event ID after reschedule: {new_event_id}")
                    else:
                        log.error(f"Failed to force update Google Calendar event for rescheduling")
            except Exception as e:
                log.error(f"Exception updating Google Calendar event: {e}")
                import traceback
                log.error(f"Traceback: {traceback.format_exc()}")

            try:
                sched = _get_scheduler_safe()
                if sched:
                    await ReminderService.cancel_for_booking(sched, booking_id)
                    await ReminderService.schedule_for_booking(sched, booked)
            except Exception as e:
                log.error(f"Exception rescheduling reminders for booking {booking_id}: {e}")

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

        old_contact = booking.student_contact
        changed = False
        if student_name is not None and booking.student_name != student_name:
            booking.student_name = student_name
            changed = True
        if contact is not None and booking.student_contact != contact:
            booking.student_contact = contact
            changed = True

        if changed:
            await session.commit()
            log.info(f"Updated booking {booking_id}: student_name={booking.student_name}, contact={booking.student_contact}")
            
            try:
                if settings.google_calendar_enabled and booking.gcal_event_id:
                    log.info(f"Force updating Google Calendar event {booking.gcal_event_id} for booking {booking_id}")
                    
                    # Используем принудительное обновление с пересозданием
                    new_event_id = GoogleCalendarService.force_update_event(
                        booking.gcal_event_id,
                        booking.slot.start_at,
                        booking.student_name,
                        booking.student_contact,
                        booking.id  # Передаем правильный booking_id
                    )
                    
                    if new_event_id:
                        log.info(f"Successfully force updated Google Calendar event for booking {booking_id}")
                        # Обновляем ID события в базе данных
                        booking.gcal_event_id = new_event_id
                        await session.commit()
                        log.info(f"Updated booking with new event ID: {new_event_id}")
                    else:
                        log.error(f"Failed to force update Google Calendar event for booking {booking_id}")
                else:
                    log.warning(f"Google Calendar disabled or no event ID for booking {booking_id}")
            except Exception as e:
                log.error(f"Exception updating Google Calendar event content: {e}")
                import traceback
                log.error(f"Traceback: {traceback.format_exc()}")
        else:
            log.info(f"No changes detected for booking {booking_id}")
        return True

    @staticmethod
    async def book_interval(
        session,
        user: User,
        weekday: int,
        time_str: str,
        student_name: str,
        contact: Optional[str] = None,
    ) -> Optional[Booking]:
        """Бронирование интервального занятия"""
        
        # Проверяем, не занято ли уже это время для интервальных занятий
        existing = await session.scalar(
            select(Booking.id)
            .where(
                Booking.lesson_type == "interval",
                Booking.weekday == weekday,
                Booking.time_hhmm == time_str
            )
            .limit(1)
        )
        if existing is not None:
            return None

        # Создаем интервальное занятие
        booking = Booking(
            user_id=user.id,
            slot_id=None,  # Для интервальных занятий slot_id может быть None
            student_name=student_name,
            student_contact=(contact or None),
            lesson_type="interval",
            weekday=weekday,
            time_hhmm=time_str,
        )
        session.add(booking)
        await session.flush()
        await session.commit()

        booked = await session.scalar(
            select(Booking)
            .where(Booking.id == booking.id)
        )

        # Создаем события в Google Calendar для интервальных занятий
        try:
            if settings.google_calendar_enabled and booked:
                # Создаем события для ближайших 4 недель
                from datetime import datetime, timedelta, time
                from zoneinfo import ZoneInfo
                
                now = datetime.now(ZoneInfo(settings.tz))
                weekday_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
                
                # Находим ближайшие даты с этим днем недели
                for week in range(4):  # 4 недели вперед
                    for day_offset in range(7):
                        target_date = now.date() + timedelta(days=week * 7 + day_offset)
                        if target_date.weekday() == weekday:
                            hour, minute = map(int, time_str.split(':'))
                            start_at = datetime.combine(target_date, time(hour=hour, minute=minute))
                            start_at = start_at.replace(tzinfo=ZoneInfo(settings.tz))
                            
                            # Создаем событие только для будущих дат
                            if start_at > now:
                                ev_id = GoogleCalendarService.create_event(
                                    booked.id,
                                    start_at,
                                    f"{booked.student_name} ({weekday_names[weekday]})",
                                    booked.student_contact,
                                )
                                if ev_id:
                                    log.info(f"Created Google Calendar event for interval booking: {ev_id} for {start_at}")
                                break  # Создаем только одно событие на неделю
        except Exception as e:
            log.error(f"Exception creating Google Calendar events for interval booking {booked.id}: {e}")

        # Отправляем немедленное уведомление на email для интервальных занятий
        try:
            if booked and settings.smtp_enabled and EmailService.is_email(booked.student_contact):
                weekday_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
                weekday_name = weekday_names[weekday] if weekday is not None else "Неизвестно"
                
                success = EmailService.send(
                    to_email=booked.student_contact,
                    subject="Подтверждение записи на интервальное занятие",
                    body=f"Здравствуйте!\n\nВы успешно записаны на интервальное занятие:\n"
                         f"День недели: {weekday_name}\n"
                         f"Время: {time_str}\n"
                         f"Ученик: {booked.student_name}\n"
                         f"Контакт: {booked.student_contact}\n\n"
                         f"Занятие будет повторяться каждую неделю в это время.\n"
                         f"Запись #{booked.id}\n\n"
                         f"С уважением,\nРепетитор"
                )
                if success:
                    log.info(f"Sent confirmation email to {booked.student_contact} for interval booking {booked.id}")
                else:
                    log.warning(f"Failed to send confirmation email to {booked.student_contact} for interval booking {booked.id}")
            else:
                log.info(f"Email disabled or invalid email address for interval booking: {booked.student_contact if booked else 'None'}")
        except Exception as e:
            log.error(f"Failed to send confirmation email for interval booking {booked.id if booked else 'None'}: {e}")

        return booked