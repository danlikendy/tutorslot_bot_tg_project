from __future__ import annotations

from datetime import datetime, date
from typing import cast, Optional
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery

from app.services.slot_service import SlotService
from app.services.booking_service import BookingService
from app.bot.keyboards.common import (
    kb_days_with_counts,
    kb_times_for_day,
    # kb_my_bookings,
)
from app.storage.db import SessionLocal
from app.config import settings
from app.utils.dates import format_day_ru, format_dt_ru
from app.storage.models import WeeklySubscription

router = Router(name="booking")
TZ = ZoneInfo(settings.tz)

class BookingFSM(StatesGroup):
    waiting_name = State()
    waiting_contact = State()

async def _busy_weekly_hhmm_for_day(session, day: date) -> set[str]:
    wday = day.weekday()  # Пн=0..Вс=6
    rows = await session.execute(
        WeeklySubscription.__table__.select().where(
            WeeklySubscription.weekday == wday,
            WeeklySubscription.is_active == True,
        )
    )
    return {m["time_hhmm"] for m in rows.mappings().all()}

@router.callback_query(F.data.startswith("day:"))
async def pick_day(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None
    msg = cast(Message, cb.message)

    iso = cb.data.split(":", 1)[1]
    day = date.fromisoformat(iso)

    async with SessionLocal() as session:
        times = await SlotService.available_times_for_day(session, day)
        busy = await _busy_weekly_hhmm_for_day(session, day)
        times = [t for t in times if t.strftime("%H:%M") not in busy]

    await msg.answer(
        f"Доступное время на {format_day_ru(day)}:",
        reply_markup=kb_times_for_day(times),
    )
    await cb.answer()

@router.callback_query(F.data.startswith("time:"))
async def pick_time(cb: CallbackQuery, state: FSMContext):
    assert cb.message is not None and cb.data is not None
    msg = cast(Message, cb.message)

    iso = cb.data.split(":", 1)[1]
    await state.update_data(picked_start_at=iso)

    await msg.answer("Введите имя ученика:")
    await state.set_state(BookingFSM.waiting_name)
    await cb.answer()

@router.message(BookingFSM.waiting_name, F.text & ~F.text.startswith("/"))
async def fill_name(message: Message, state: FSMContext):
    student_name = (message.text or "").strip()
    if not student_name:
        await message.answer("Имя пустое. Введите имя ученика:")
        return

    await state.update_data(student_name=student_name)
    await message.answer("Укажите контакт (почта):")
    await state.set_state(BookingFSM.waiting_contact)

@router.message(BookingFSM.waiting_contact, F.text & ~F.text.startswith("/"))
async def confirm_booking(message: Message, state: FSMContext):
    data = await state.get_data()
    iso = data.get("picked_start_at")
    if not iso:
        await state.clear()
        await message.answer("Слот потерян. Начните заново: /start")
        return

    contact = (message.text or "").strip()
    if not contact:
        await message.answer("Контакт пустой. Укажите телефон или почту:")
        return

    start_at = datetime.fromisoformat(iso)
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=TZ)

    if start_at <= datetime.now(TZ):
        async with SessionLocal() as session:
            days = await SlotService.available_days(session)
        await message.answer(
            "Нельзя бронировать прошедшее время. Выберите день:",
            reply_markup=kb_days_with_counts(list(days.items())),
        )
        return

    assert message.from_user is not None
    student_name = (data.get("student_name") or (message.from_user.full_name or "Ученик")).strip()

    booked_at: Optional[datetime] = None
    async with SessionLocal() as session:
        user = await BookingService.ensure_user(session, message.from_user.id, message.from_user.full_name or "")
        booking = await BookingService.book_at(session, user, start_at, student_name, contact)
        if booking is None:
            async with SessionLocal() as s2:
                days = await SlotService.available_days(s2)
            await message.answer(
                "Слот уже занят. Выберите другой день:",
                reply_markup=kb_days_with_counts(list(days.items())),
            )
            await state.clear()
            return

        booked_at = booking.slot.start_at
        if booked_at.tzinfo is None:
            booked_at = booked_at.replace(tzinfo=TZ)
        student_name = booking.student_name
        contact = booking.student_contact

    await state.clear()

    await message.answer(
        f"Вы записаны: {format_dt_ru(booked_at.astimezone(TZ))}\n"
        f"Имя: {student_name}\nКонтакт: {contact}"
    )

@router.message(F.text == "Мои записи")
@router.message(Command("my"))
async def my_bookings(message: Message):
    assert message.from_user is not None

    async with SessionLocal() as session:
        user = await BookingService.ensure_user(session, message.from_user.id, message.from_user.full_name or "")
        bookings = await BookingService.my_bookings(session, user)

    if not bookings:
        await message.answer("У вас пока нет записей")
        return

    lines: list[str] = []
    for b in bookings:
        start_at: datetime = b.slot.start_at
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=TZ)
        when = format_dt_ru(start_at.astimezone(TZ))
        student = (b.student_name or "Ученик")
        contact = (b.student_contact or "")
        lines.append(f"#{b.id}: {when}\n— {student} {f'({contact})' if contact else ''}")

    await message.answer("Ваши записи:\n\n" + "\n\n".join(lines))