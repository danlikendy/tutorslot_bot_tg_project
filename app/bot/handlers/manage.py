from __future__ import annotations
from datetime import date, datetime
from typing import cast

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.services.slot_service import SlotService
from app.services.booking_service import BookingService
from app.bot.keyboards.common import (
    kb_admin_bookings,
    kb_admin_edit_menu,
    kb_admin_days,
    kb_admin_times,
    kb_days_with_counts,
)
from app.storage.models import Booking
from app.storage.db import SessionLocal
from app.utils.dates import format_dt_ru

from zoneinfo import ZoneInfo
from app.runtime import get_scheduler
from app.services.reminder_service import ReminderService

TZ = ZoneInfo(settings.tz)
router = Router(name="manage")

def is_admin(user_id: int) -> bool:
    return user_id in settings.admins

ADMIN_EDIT: dict[int, int] = {}
ADMIN_EDIT_ACTION: dict[int, tuple[str, int]] = {}

async def _render_active_bookings_text() -> str:
    async with SessionLocal() as session:
        res = await session.execute(
            select(Booking)
            .options(selectinload(Booking.slot))
            .order_by(Booking.id.desc())
        )
        bookings = list(res.scalars().all())

    if not bookings:
        return "Броней нет"

    lines: list[str] = []
    for b in bookings:
        dt = b.slot.start_at
        lines.append(
            f"{format_dt_ru(dt)}\n"
            f"Имя: {b.student_name or '—'}\n"
            f"Контакт: {b.student_contact or '—'}"
        )
    return "\n\n".join(lines)

@router.message(Command("admin"))
async def admin_panel(message: Message):
    assert message.from_user is not None
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав")
        return

    async with SessionLocal() as session:
        res = await session.execute(
            select(Booking).options(selectinload(Booking.slot)).order_by(Booking.id.desc())
        )
        all_bookings = list(res.scalars().all())

    await message.answer(
        "Админ-панель (все записи):",
        reply_markup=kb_admin_bookings(all_bookings),
    )

@router.callback_query(F.data.startswith("a:cancel:"))
async def a_cancel(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None and cb.from_user is not None
    msg = cast(Message, cb.message)
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return

    booking_id = int(cb.data.split(":", 2)[2])

    async with SessionLocal() as session:
        res = await session.execute(
            select(Booking).options(selectinload(Booking.slot)).where(Booking.id == booking_id)
        )
        bk = res.scalar_one_or_none()
        if bk is None:
            await cb.answer("Запись не найдена", show_alert=True)
            return

        student = bk.student_name or "—"
        when = bk.slot.start_at

        ok = await BookingService.admin_cancel(session, booking_id)

        res2 = await session.execute(
            select(Booking).options(selectinload(Booking.slot)).order_by(Booking.id.desc())
        )
        all_bookings = list(res2.scalars().all())

    await msg.answer(
        f"Ученик {student} на дату {when:%d.%m %H:%M} отменён" if ok else "Не удалось отменить запись"
    )
    await msg.answer("Админ-панель (все записи):", reply_markup=kb_admin_bookings(all_bookings))
    await cb.answer()

@router.callback_query(F.data.startswith("a:edit:"))
async def a_edit_menu(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None and cb.from_user is not None
    msg = cast(Message, cb.message)
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return

    booking_id = int(cb.data.split(":", 2)[2])
    ADMIN_EDIT[cb.from_user.id] = booking_id
    ADMIN_EDIT_ACTION.pop(cb.from_user.id, None)

    await msg.answer("Что изменить?", reply_markup=kb_admin_edit_menu(booking_id))
    await cb.answer()

@router.callback_query(F.data.startswith("a:edit_done:"))
async def a_edit_done(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None and cb.from_user is not None
    msg = cast(Message, cb.message)
    ADMIN_EDIT.pop(cb.from_user.id, None)
    ADMIN_EDIT_ACTION.pop(cb.from_user.id, None)

    text = await _render_active_bookings_text()
    await msg.answer(text)
    await cb.answer()

@router.callback_query(F.data.startswith("a:edit_date:"))
async def a_edit_date(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None and cb.from_user is not None
    msg = cast(Message, cb.message)
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return

    booking_id = int(cb.data.split(":", 2)[2])
    ADMIN_EDIT[cb.from_user.id] = booking_id
    async with SessionLocal() as session:
        days = await SlotService.available_days(session)
    await msg.answer(
        f"Выберите новый день (изменение даты #{booking_id}):",
        reply_markup=kb_admin_days(list(days.items()), booking_id),
    )
    await cb.answer()

@router.callback_query(F.data.startswith("ed:day:"))
async def a_edit_day_pick(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None
    msg = cast(Message, cb.message)

    _, _, bid, date_iso = cb.data.split(":", 3)
    booking_id = int(bid)
    day = date.fromisoformat(date_iso)

    async with SessionLocal() as session:
        times = await SlotService.available_times_for_day(session, day)

    await msg.answer(
        f"Выберите новое время (#{booking_id}):",
        reply_markup=kb_admin_times(times, booking_id),
    )
    await cb.answer()

@router.callback_query(F.data.startswith("ed:time:"))
async def a_edit_time_apply(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None
    msg = cast(Message, cb.message)

    _, _, bid, iso = cb.data.split(":", 3)
    booking_id = int(bid)
    new_start = datetime.fromisoformat(iso)

    async with SessionLocal() as session:
        updated = await BookingService.reschedule_to(session, booking_id, new_start)

    await msg.answer("Дата/время обновлены" if updated else "Не удалось (время занято)")
    await msg.answer("Что дальше изменить?", reply_markup=kb_admin_edit_menu(booking_id))
    await cb.answer()

@router.callback_query(F.data.startswith("a:edit_name:"))
async def a_edit_name(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None and cb.from_user is not None
    msg = cast(Message, cb.message)
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return
    booking_id = int(cb.data.split(":", 2)[2])
    ADMIN_EDIT[cb.from_user.id] = booking_id
    ADMIN_EDIT_ACTION[cb.from_user.id] = ("name", booking_id)
    await msg.answer("Введите новое имя ученика:")
    await cb.answer()

@router.callback_query(F.data.startswith("a:edit_contact:"))
async def a_edit_contact(cb: CallbackQuery):
    assert cb.message is not None and cb.data is not None and cb.from_user is not None
    msg = cast(Message, cb.message)
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return
    booking_id = int(cb.data.split(":", 2)[2])
    ADMIN_EDIT[cb.from_user.id] = booking_id
    ADMIN_EDIT_ACTION[cb.from_user.id] = ("contact", booking_id)
    await msg.answer("Введите новый контакт (почта):")
    await cb.answer()

@router.message(
    F.text & ~F.text.startswith("/") &
    F.from_user.func(lambda u: u is not None) &
    F.from_user.func(lambda u: ADMIN_EDIT_ACTION.get(u.id) is not None)
)
async def a_edit_apply(message: Message):
    if message.from_user is None:
        return
    action = ADMIN_EDIT_ACTION.get(message.from_user.id)
    if not action:
        return

    what, booking_id = action
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустое значение. Введите ещё раз")
        return

    async with SessionLocal() as session:
        if what == "name":
            updated = await BookingService.admin_update_content(session, booking_id, student_name=text)
        else:
            updated = await BookingService.admin_update_content(session, booking_id, contact=text)

    await message.answer("Обновлено" if updated else "Не удалось обновить")
    await message.answer("Что дальше изменить?", reply_markup=kb_admin_edit_menu(booking_id))
    ADMIN_EDIT_ACTION.pop(message.from_user.id, None)

@router.message(Command("ids"))
async def admin_ids(message: Message):
    assert message.from_user is not None
    if not is_admin(message.from_user.id):
        await message.answer("Нет прав")
        return
    async with SessionLocal() as session:
        res = await session.execute(
            select(Booking).options(selectinload(Booking.slot)).order_by(Booking.id.desc())
        )
        bs = list(res.scalars().all())
    if not bs:
        await message.answer("Записей нет")
        return
    lines = [f"#{b.id} — {b.slot.start_at:%d.%m %H:%M} • {b.student_name} ({b.student_contact or '—'})" for b in bs]
    await message.answer("\n".join(lines))

@router.message(Command("jobs"))
async def admin_jobs(message: Message):
    assert message.from_user is not None
    if not is_admin(message.from_user.id):
        await message.answer("Нет прав")
        return
    s = get_scheduler()
    jobs = s.get_jobs()
    if not jobs:
        await message.answer("Задач нет")
        return
    lines = []
    for j in jobs:
        nxt = j.next_run_time.astimezone(TZ).strftime("%d.%m %H:%M:%S") if j.next_run_time else "—"
        lines.append(f"{j.id} → {nxt}")
    await message.answer("Активные задачи:\n" + "\n".join(lines))

@router.message(Command("remindnow"))
async def admin_remind_now(message: Message):
    assert message.from_user is not None
    if not is_admin(message.from_user.id):
        await message.answer("Нет прав")
        return
    try:
        parts = (message.text or "").split()
        bid = int(parts[1])
    except Exception:
        await message.answer("Формат: /remindnow <booking_id>")
        return
    await ReminderService.send_reminder_job(bid)
    await message.answer(f"Ок, отправил напоминание для #{bid}")