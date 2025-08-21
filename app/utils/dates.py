from __future__ import annotations
from datetime import date, datetime

_DAYS_RU_SHORT = {
    "Mon": "Пн",
    "Tue": "Вт",
    "Wed": "Ср",
    "Thu": "Чт",
    "Fri": "Пт",
    "Sat": "Сб",
    "Sun": "Вс",
}

def day_short_ru(d: date | datetime) -> str:
    key = d.strftime("%a")
    return _DAYS_RU_SHORT.get(key, key)

def format_day_ru(d: date, with_count: int | None = None) -> str:
    base = f"{day_short_ru(d)} {d.strftime('%d.%m')}"
    return f"{base} ({with_count})" if with_count is not None else base

def format_dt_ru(dt: datetime) -> str:
    return f"{day_short_ru(dt)} {dt.strftime('%d.%m %H:%M')}"