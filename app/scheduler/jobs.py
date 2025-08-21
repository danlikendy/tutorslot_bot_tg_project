from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.storage.models import Booking
from app.services.reminder_service import ReminderService

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