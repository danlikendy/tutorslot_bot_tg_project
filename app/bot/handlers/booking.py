from __future__ import annotations

from datetime import datetime, date
from typing import cast, Optional
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.services.slot_service import SlotService
from app.services.booking_service import BookingService
from app.storage.models import Booking
from app.bot.keyboards.common import (
    kb_days_with_counts,
    kb_times_for_day,
    kb_lesson_types,
    kb_weekdays,
    kb_interval_times,
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
    # Для интервальных занятий
    waiting_weekday = State()
    waiting_interval_time = State()

async def _busy_weekly_hhmm_for_day(session, weekday: int) -> set[str]:
    """Получаем занятые времена для дня недели в интервальных записях"""
    rows = await session.execute(
        select(Booking.time_hhmm).where(
            Booking.lesson_type == "interval",
            Booking.weekday == weekday,
        )
    )
    return {row[0] for row in rows.all() if row[0] is not None}

@router.callback_query(F.data.startswith("lesson_type:"))
async def pick_lesson_type(cb: CallbackQuery, state: FSMContext):
    """Обработчик выбора типа занятия"""
    assert cb.message is not None and cb.data is not None
    msg = cast(Message, cb.message)
    
    lesson_type = cb.data.split(":", 1)[1]
    await state.update_data(lesson_type=lesson_type)
    
    if lesson_type == "single":
        # Одиночное занятие - показываем дни
        async with SessionLocal() as session:
            days = await SlotService.available_days(session)
        await msg.answer(
            "Выберите день:",
            reply_markup=kb_days_with_counts(list(days.items())),
        )
    elif lesson_type == "interval":
        # Интервальное занятие - показываем дни недели
        await msg.answer(
            "Выберите день недели:",
            reply_markup=kb_weekdays(),
        )
        await state.set_state(BookingFSM.waiting_weekday)
    
    await cb.answer()

@router.callback_query(F.data.startswith("weekday:"), BookingFSM.waiting_weekday)
async def pick_weekday(cb: CallbackQuery, state: FSMContext):
    """Обработчик выбора дня недели для интервального занятия"""
    assert cb.message is not None and cb.data is not None
    msg = cast(Message, cb.message)
    
    weekday = int(cb.data.split(":", 1)[1])
    await state.update_data(weekday=weekday)
    
    # Получаем занятые времена для этого дня недели
    async with SessionLocal() as session:
        busy_times = await _busy_weekly_hhmm_for_day(session, weekday)
    
    await msg.answer(
        "Выберите время:",
        reply_markup=kb_interval_times(busy_times),
    )
    await state.set_state(BookingFSM.waiting_interval_time)
    await cb.answer()

@router.callback_query(F.data.startswith("interval_time:"), BookingFSM.waiting_interval_time)
async def pick_interval_time(cb: CallbackQuery, state: FSMContext):
    """Обработчик выбора времени для интервального занятия"""
    assert cb.message is not None and cb.data is not None
    msg = cast(Message, cb.message)
    
    time_str = cb.data.split(":", 1)[1]
    await state.update_data(interval_time=time_str)
    
    await msg.answer("Введите имя ученика:")
    await state.set_state(BookingFSM.waiting_name)
    await cb.answer()

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
    lesson_type = data.get("lesson_type", "single")
    
    contact = (message.text or "").strip()
    if not contact:
        await message.answer("Контакт пустой. Укажите телефон или почту:")
        return

    assert message.from_user is not None
    student_name = (data.get("student_name") or (message.from_user.full_name or "Ученик")).strip()

    if lesson_type == "single":
        # Обработка одиночного занятия
        iso = data.get("picked_start_at")
        if not iso:
            await state.clear()
            await message.answer("Слот потерян. Начните заново: /start")
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

        booked_at: Optional[datetime] = None
        async with SessionLocal() as session:
            user = await BookingService.ensure_user(session, message.from_user.id, message.from_user.full_name or "")
            booking = await BookingService.book_at(session, user, start_at, student_name, contact, lesson_type="single")
            if booking is None:
                async with SessionLocal() as s2:
                    days = await SlotService.available_days(s2)
                await message.answer(
                    "Слот уже занят. Выберите другой день:",
                    reply_markup=kb_days_with_counts(list(days.items())),
                )
                await state.clear()
                return

            if booking.slot:
                booked_at = booking.slot.start_at
                if booked_at.tzinfo is None:
                    booked_at = booked_at.replace(tzinfo=TZ)
            else:
                # Для интервальных занятий без слота
                booked_at = None
            student_name = booking.student_name
            contact = booking.student_contact

        await state.clear()
        if booked_at:
            await message.answer(
                f"Вы записаны: {format_dt_ru(booked_at.astimezone(TZ))}\n"
                f"Имя: {student_name}\nКонтакт: {contact}"
            )
        else:
            await message.answer(
                f"Вы записаны на интервальное занятие\n"
                f"Имя: {student_name}\nКонтакт: {contact}"
            )
    
    elif lesson_type == "interval":
        # Обработка интервального занятия
        weekday = data.get("weekday")
        time_str = data.get("interval_time")
        
        if weekday is None or time_str is None:
            await state.clear()
            await message.answer("Данные потеряны. Начните заново: /start")
            return

        async with SessionLocal() as session:
            user = await BookingService.ensure_user(session, message.from_user.id, message.from_user.full_name or "")
            booking = await BookingService.book_interval(
                session, user, weekday, time_str, student_name, contact
            )
            if booking is None:
                await message.answer(
                    "Это время уже занято для интервальных занятий. Выберите другое время:",
                    reply_markup=kb_interval_times(),
                )
                await state.set_state(BookingFSM.waiting_interval_time)
                return

        await state.clear()
        weekday_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"]
        await message.answer(
            f"Интервальное занятие записано:\n"
            f"День: {weekday_names[weekday]}\n"
            f"Время: {time_str}\n"
            f"Имя: {student_name}\n"
            f"Контакт: {contact}\n\n"
            f"Занятие будет повторяться каждую неделю в это время."
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
        if b.lesson_type == "interval":
            # Интервальное занятие - показываем день недели и время
            weekday_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            weekday_name = weekday_names[b.weekday] if b.weekday is not None else "Неизвестно"
            when = f"{weekday_name} {b.time_hhmm}"
        else:
            # Одиночное занятие - показываем конкретную дату и время
            if b.slot is None:
                continue  # Пропускаем записи без слота (не должно происходить для single)
            start_at: datetime = b.slot.start_at
            if start_at.tzinfo is None:
                start_at = start_at.replace(tzinfo=TZ)
            when = format_dt_ru(start_at.astimezone(TZ))
        
        student = (b.student_name or "Ученик")
        contact = (b.student_contact or "")
        lesson_type_text = "Интервальное" if b.lesson_type == "interval" else "Одиночное"
        lines.append(f"#{b.id}: {when} ({lesson_type_text})\n— {student} {f'({contact})' if contact else ''}")

    await message.answer("Ваши записи:\n\n" + "\n\n".join(lines))