from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.storage.models import WeeklySubscription, User
from app.services.google_calendar_service import GoogleCalendarService
from app.services.reminder_service import ReminderService
from app.config import settings

class WeeklyService:
    @staticmethod
    async def create_subscription(session, user: User, weekday: int, time_hhmm: str,
                                  student_name: str, contact: str | None, duration_min: int = 60) -> WeeklySubscription:
        sub = WeeklySubscription(
            user_id=user.id,
            student_name=student_name,
            student_contact=contact,
            weekday=weekday,
            time_hhmm=time_hhmm,
            duration_min=duration_min,
            is_active=True,
        )
        session.add(sub)
        await session.flush()

        if settings.google_calendar_enabled:
            ev_id = GoogleCalendarService.create_recurring_event(
                summary=f"Занятие: {student_name}",
                weekday=weekday,
                time_hhmm=time_hhmm,
                duration_min=duration_min,
                attendee_email=contact,
                timezone=settings.tz,
            )
            if ev_id:
                sub.gcal_event_id = ev_id

        await session.commit()

        try:
            from app.main import get_scheduler
            sched = get_scheduler()
            if sched:
                await ReminderService.schedule_for_weekly(sched, sub, tz_name=settings.tz)
        except Exception:
            pass

        return sub

    @staticmethod
    async def cancel_subscription(session, sub_id: int) -> bool:
        sub = await session.scalar(select(WeeklySubscription).where(WeeklySubscription.id == sub_id))
        if not sub:
            return False
        sub.is_active = False
        await session.flush()
        await session.commit()

        try:
            from app.main import get_scheduler
            sched = get_scheduler()
            if sched:
                await ReminderService.cancel_for_weekly(sched, sub_id)
        except Exception:
            pass

        try:
            if sub.gcal_event_id:
                GoogleCalendarService.delete_recurring_series(sub.gcal_event_id)
        except Exception:
            pass

        return True