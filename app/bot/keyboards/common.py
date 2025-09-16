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
            if b.lesson_type == "interval":
                weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                weekday_name = weekday_names[b.weekday] if b.weekday is not None else "—"
                text = f"{weekday_name} {b.time_hhmm} • {b.student_name} (интервал)"
            else:
                if b.slot is None:
                    continue  # Пропускаем записи без слота
                dt = b.slot.start_at
                text = f"{dt:%d.%m %H:%M} • {b.student_name}"
            kb.button(text=text, callback_data="noop")
    kb.adjust(1)
    return kb.as_markup()

def kb_admin_bookings(bookings: Sequence[Booking]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not bookings:
        b.row(InlineKeyboardButton(text="Броней нет", callback_data="noop"))
        return b.as_markup()

    single_bookings = [bk for bk in bookings if bk.lesson_type == "single"]
    interval_bookings = [bk for bk in bookings if bk.lesson_type == "interval"]

    if single_bookings:
        b.row(InlineKeyboardButton(text="=== ОДИНОЧНЫЕ ЗАНЯТИЯ ===", callback_data="noop"))
        for bk in single_bookings:
            if bk.slot:
                dt = bk.slot.start_at
                text = f"{dt:%d.%m %H:%M} • {bk.student_name}"
            else:
                text = f"Без слота • {bk.student_name}"
            b.row(InlineKeyboardButton(text=text, callback_data="noop"))
            b.row(
                InlineKeyboardButton(text="Изменить", callback_data=f"a:edit:{bk.id}"),
                InlineKeyboardButton(text="Отменить", callback_data=f"a:cancel:{bk.id}"),
            )

    if interval_bookings:
        if single_bookings:
            b.row(InlineKeyboardButton(text="", callback_data="noop"))  # Пустая строка
        b.row(InlineKeyboardButton(text="=== ИНТЕРВАЛЬНЫЕ ЗАНЯТИЯ ===", callback_data="noop"))
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт"]
        for bk in interval_bookings:
            weekday_name = weekday_names[bk.weekday] if bk.weekday is not None else "—"
            time_str = bk.time_hhmm or "—"
            b.row(InlineKeyboardButton(text=f"{weekday_name} {time_str} • {bk.student_name}", callback_data="noop"))
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

def kb_lesson_types() -> InlineKeyboardMarkup:
    """Клавиатура для выбора типа занятия"""
    kb = InlineKeyboardBuilder()
    kb.button(text="Одиночное занятие", callback_data="lesson_type:single")
    kb.button(text="Интервальное занятие", callback_data="lesson_type:interval")
    kb.adjust(1)
    return kb.as_markup()

def kb_weekdays() -> InlineKeyboardMarkup:
    """Клавиатура для выбора дня недели"""
    kb = InlineKeyboardBuilder()
    weekdays = [
        ("Понедельник", 0),
        ("Вторник", 1), 
        ("Среда", 2),
        ("Четверг", 3),
        ("Пятница", 4)
    ]
    for name, day_num in weekdays:
        kb.button(text=name, callback_data=f"weekday:{day_num}")
    kb.adjust(1)
    return kb.as_markup()

def kb_interval_times(busy_times: set[str] | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для выбора времени интервального занятия"""
    kb = InlineKeyboardBuilder()
    times = ["16:00", "17:45", "19:30"]
    busy_times = busy_times or set()
    
    for time_str in times:
        if time_str not in busy_times:
            # Показываем только свободные времена
            kb.button(text=time_str, callback_data=f"interval_time:{time_str}")
    kb.adjust(1)
    return kb.as_markup()