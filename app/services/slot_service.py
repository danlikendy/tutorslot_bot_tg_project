from __future__ import annotations
from datetime import datetime, timedelta, time, date
from typing import Iterable, List, Dict

from sqlalchemy import select, join
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Slot, Booking

WEEKDAY_HOURS = (15, 17, 19)
WINDOW_DAYS = 14

def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)

def _is_weekday(d: date) -> bool:
    return d.weekday() < 5

def _generate_all_candidates(start: datetime, days: int) -> List[datetime]:
    start_day = _start_of_day(start)
    out: List[datetime] = []
    for i in range(days):
        day = (start_day + timedelta(days=i)).date()
        if not _is_weekday(day):
            continue
        for h in WEEKDAY_HOURS:
            out.append(datetime.combine(day, time(hour=h)))
    return out

async def _occupied_datetimes(session: AsyncSession) -> set[datetime]:
    j = join(Slot, Booking, Slot.id == Booking.slot_id)
    res = await session.execute(select(Slot.start_at).select_from(j))
    return set(res.scalars().all())

class SlotService:
    @staticmethod
    async def available_days(session: AsyncSession, *, now: datetime | None = None) -> Dict[date, int]:
        now = now or datetime.now()
        candidates = _generate_all_candidates(now, WINDOW_DAYS)
        busy = await _occupied_datetimes(session)
        free = [dt for dt in candidates if dt not in busy and dt >= now]
        # агрегируем по дню
        counts: Dict[date, int] = {}
        for dt in free:
            counts[dt.date()] = counts.get(dt.date(), 0) + 1
        return {d: c for d, c in sorted(counts.items()) if c > 0}

    @staticmethod
    async def available_times_for_day(session: AsyncSession, target_day: date, *, now: datetime | None = None) -> List[datetime]:
        now = now or datetime.now()
        day_candidates = [datetime.combine(target_day, time(h)) for h in WEEKDAY_HOURS]
        busy = await _occupied_datetimes(session)
        return [dt for dt in day_candidates if dt not in busy and dt >= now]

    @staticmethod
    async def list_all_booked(session: AsyncSession) -> list[Slot]:
        res = await session.execute(select(Slot).order_by(Slot.start_at))
        return list(res.scalars().all())