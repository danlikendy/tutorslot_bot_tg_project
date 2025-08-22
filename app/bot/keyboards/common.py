from __future__ import annotations
from datetime import date, datetime
from typing import Iterable, Sequence

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.storage.models import Booking
from app.utils.dates import format_day_ru

def kb_days_with_counts(days: Sequence[tuple[date, int]]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d, cnt in days:
        kb.button(text=f"{format_day_ru(d)} ({cnt})", callback_data=f"day:{d.isoformat()}")
    kb.adjust(1)
    return kb.as_markup()

def kb_times_for_day(times: Iterable[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in times:
        kb.button(text=t.strftime("%H:%M"), callback_data=f"time:{t.isoformat()}")
    kb.adjust(1)
    return kb.as_markup()

def kb_my_bookings(bookings: Sequence[Booking]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not bookings:
        kb.button(text="Броней нет", callback_data="noop")
    else:
        for b in bookings:
            dt = b.slot.start_at
            kb.button(text=f"{dt:%d.%m %H:%M} • {b.student_name}", callback_data="noop")
    kb.adjust(1)
    return kb.as_markup()

def kb_admin_bookings(bookings: Sequence[Booking]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not bookings:
        b.row(InlineKeyboardButton(text="Броней нет", callback_data="noop"))
        return b.as_markup()

    for bk in bookings:
        dt = bk.slot.start_at
        b.row(InlineKeyboardButton(text=f"{dt:%d.%m %H:%M} • {bk.student_name}", callback_data="noop"))
        b.row(
            InlineKeyboardButton(text="Изменить", callback_data=f"a:edit:{bk.id}"),
            InlineKeyboardButton(text="Отменить", callback_data=f"a:cancel:{bk.id}"),
        )
    return b.as_markup()

def kb_admin_edit_menu(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Изменить дату", callback_data=f"a:edit_date:{booking_id}")
    kb.button(text="Изменить имя", callback_data=f"a:edit_name:{booking_id}")
    kb.button(text="Изменить контакт", callback_data=f"a:edit_contact:{booking_id}")
    kb.button(text="Готово", callback_data=f"a:edit_done:{booking_id}")
    kb.adjust(1)
    return kb.as_markup()

def kb_admin_days(days: Sequence[tuple[date, int]], booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d, cnt in days:
        kb.button(
            text=f"{format_day_ru(d)} ({cnt})",
            callback_data=f"ed:day:{booking_id}:{d.isoformat()}",
        )
    kb.adjust(1)
    return kb.as_markup()

def kb_admin_times(times: Iterable[datetime], booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in times:
        kb.button(text=t.strftime("%H:%M"), callback_data=f"ed:time:{booking_id}:{t.isoformat()}")
    kb.adjust(1)
    return kb.as_markup()