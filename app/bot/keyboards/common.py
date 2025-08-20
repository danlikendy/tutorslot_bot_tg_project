from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.storage.models import Slot, Booking

def kb_slots(slots: list[Slot]) -> InlineKeyboardMarkup:
    rows = []
    for s in slots:
        rows.append([InlineKeyboardButton(text=s.start_at.strftime("%a %d.%m %H:%M"), callback_data=f"book:{s.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="Нет свободных слотов", callback_data="noop")]])

def kb_my_bookings(bookings: list[Booking]) -> InlineKeyboardMarkup:
    rows = []
    for b in bookings:
        label = b.slot.start_at.strftime("%a %d.%m %H:%M")
        rows.append([
            InlineKeyboardButton(text=f"Перенести {label}", callback_data=f"reschedule:{b.id}"),
            InlineKeyboardButton(text=f"Отменить", callback_data=f"cancel:{b.id}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="Нет записей", callback_data="noop")]])

def kb_reschedule_slots(booking_id: int, slots: list[Slot]) -> InlineKeyboardMarkup:
    rows = []
    for s in slots:
        rows.append([InlineKeyboardButton(text=s.start_at.strftime("%a %d.%m %H:%M"), callback_data=f"do_reschedule:{booking_id}:{s.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="Нет свободных слотов", callback_data="noop")]])

def kb_admin(slots_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Свободные слоты ({slots_count})", callback_data="admin:free")],
        [InlineKeyboardButton(text="Добавить слот +30 мин от текущего дня 15/17/19", callback_data="admin:add_template")],
    ])