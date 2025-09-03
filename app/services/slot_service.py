from __future__ import annotations
from datetime import datetime, timedelta, time, date
from typing import Iterable, List, Dict

from sqlalchemy import select, join
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Slot, Booking

WEEKDAY_HOURS = (16, 17, 19)  # 16:00, 17:45, 19:30
WEEKDAY_MINUTES = (0, 45, 30)  # минуты для каждого часа
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
        for h, m in zip(WEEKDAY_HOURS, WEEKDAY_MINUTES):
            out.append(datetime.combine(day, time(hour=h, minute=m)))
    return out

async def _occupied_datetimes(session: AsyncSession) -> set[datetime]:
    # Получаем занятые слоты из обычных бронирований
    j = join(Slot, Booking, Slot.id == Booking.slot_id)
    res = await session.execute(select(Slot.start_at).select_from(j))
    occupied_slots = set(res.scalars().all())
    
    # Получаем занятые слоты из интервальных занятий
    interval_bookings = await session.execute(
        select(Booking.weekday, Booking.time_hhmm)
        .where(Booking.lesson_type == "interval")
    )
    
    # Добавляем все будущие слоты для интервальных занятий
    now = datetime.now()
    for weekday, time_str in interval_bookings:
        if time_str is None:  # Пропускаем записи без времени
            continue
        # Находим все даты с этим днем недели в ближайшие 14 дней
        for i in range(14):
            day = now.date() + timedelta(days=i)
            if day.weekday() == weekday:
                try:
                    hour, minute = map(int, time_str.split(':'))
                    slot_time = datetime.combine(day, time(hour=hour, minute=minute))
                    if slot_time >= now:
                        occupied_slots.add(slot_time)
                except (ValueError, AttributeError):
                    # Пропускаем некорректные времена
                    continue
    
    return occupied_slots

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
        day_candidates = [datetime.combine(target_day, time(hour=h, minute=m)) for h, m in zip(WEEKDAY_HOURS, WEEKDAY_MINUTES)]
        busy = await _occupied_datetimes(session)
        return [dt for dt in day_candidates if dt not in busy and dt >= now]

    @staticmethod
    async def list_all_booked(session: AsyncSession) -> list[Slot]:
        res = await session.execute(select(Slot).order_by(Slot.start_at))
        return list(res.scalars().all())