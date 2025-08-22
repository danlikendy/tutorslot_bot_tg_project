from __future__ import annotations
from typing import List, Dict, Tuple
import logging

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import select, update

from app.bot.keyboards.weekly_kb import weekdays_kb, times_kb_for_weekday, TIMES
from app.config import settings
from app.runtime import get_scheduler
from app.services.booking_service import BookingService
from app.services.google_calendar_service import GoogleCalendarService
from app.services.reminder_service import ReminderService
from app.storage.db import SessionLocal
from app.storage.models import WeeklySubscription, User

router = Router(name="weekly_ui")
log = logging.getLogger("weekly")

TZ_NAME = settings.tz

def _weekday_title(w: int) -> str:
    return ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][w]

class WeeklyFSM(StatesGroup):
    waiting_name = State()
    waiting_contact = State()

LAST_WDAY: Dict[int, int] = {}
PENDING: Dict[int, Tuple[int, str]] = {}

async def _busy_times_for_weekday(session, weekday: int) -> List[str]:
    rows = await session.execute(
        select(WeeklySubscription.time_hhmm).where(
            WeeklySubscription.weekday == weekday,
            WeeklySubscription.is_active == True,
        )
    )
    return sorted({r[0] for r in rows.all()})

def _times_kb_filtered(weekday: int, busy: List[str]) -> types.InlineKeyboardMarkup:
    if not busy:
        return times_kb_for_weekday(weekday)
    rows: list[list[types.InlineKeyboardButton]] = []
    for t in TIMES:
        if t in busy:
            continue
        rows.append([types.InlineKeyboardButton(text=t, callback_data=f"wktime:{weekday}:{t}")])
    if not rows:
        rows = [[types.InlineKeyboardButton(text="Нет свободного времени", callback_data="noop")]]
    return types.InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(Command("weekly"))
@router.message(Command("weekly_add"))
async def weekly_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Еженедельная запись.\n\n"
        "1) Выберите день недели;\n"
        "2) Выберите время (15:00 / 17:00 / 19:00);\n"
        "3) Введите имя ученика, затем контакт.",
        reply_markup=weekdays_kb(),
    )

@router.message(Command("weekly_list"))
async def weekly_list(message: types.Message) -> None:
    u = message.from_user
    if u is None:
        await message.answer("Не удалось определить пользователя")
        return

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.tg_id == u.id))
        if not user:
            await message.answer("Еженедельных записей нет")
            return
        res = await session.execute(
            select(WeeklySubscription)
            .where(WeeklySubscription.user_id == user.id, WeeklySubscription.is_active == True)
            .order_by(WeeklySubscription.id.desc())
        )
        subs = list(res.scalars().all())

    if not subs:
        await message.answer("Еженедельных записей нет")
        return

    lines = []
    for s in subs:
        link = GoogleCalendarService.get_event_html_link(s.gcal_event_id) if s.gcal_event_id else None
        lnk = f" — {link}" if link else ""
        lines.append(f"#{s.id}: {_weekday_title(s.weekday)} {s.time_hhmm}{lnk}")
    await message.answer("Ваши еженедельные записи:\n" + "\n".join(lines))

@router.message(Command("weekly_del"))
async def weekly_del(message: types.Message) -> None:
    u = message.from_user
    if u is None:
        await message.answer("Команда недоступна: не удалось определить пользователя")
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply("Укажите ID: `/weekly_del 12`", parse_mode="Markdown")
        return
    try:
        sub_id = int(parts[1])
    except Exception:
        await message.reply("ID должен быть числом")
        return

    async with SessionLocal() as session:
        sub = await session.scalar(select(WeeklySubscription).where(WeeklySubscription.id == sub_id))
        if not sub:
            await message.answer("Запись не найдена")
            return

        current = await BookingService.ensure_user(session, u.id, (u.full_name or ""))
        is_admin = u.id in settings.admins
        if not is_admin and sub.user_id != current.id:
            await message.answer("Можно удалить только свою запись")
            return

        await session.execute(update(WeeklySubscription).where(WeeklySubscription.id == sub_id).values(is_active=False))
        await session.commit()

        try:
            if sub.gcal_event_id:
                GoogleCalendarService.delete_event(sub.gcal_event_id)
        except Exception:
            pass
        try:
            await ReminderService.cancel_for_weekly(get_scheduler(), sub_id)
        except Exception:
            pass

    await message.answer(f"Еженедельная запись #{sub_id} удалена")

@router.callback_query(F.data.startswith("wkday:"))
async def pick_day(cq: types.CallbackQuery):
    u = cq.from_user
    if not (cq.data and u):
        await cq.answer(); return
    try:
        wday = int(cq.data.split(":")[1])
    except Exception:
        await cq.answer(); return

    LAST_WDAY[u.id] = wday
    PENDING.pop(u.id, None)

    async with SessionLocal() as session:
        busy = await _busy_times_for_weekday(session, wday)

    if isinstance(cq.message, types.Message):
        try: await cq.message.edit_reply_markup(reply_markup=None)
        except Exception: pass
        await cq.message.answer("Выберите время:", reply_markup=_times_kb_filtered(wday, busy))
    await cq.answer()

@router.callback_query(F.data.startswith("wktime:"))
async def pick_time_prefixed(cq: types.CallbackQuery, state: FSMContext):
    u = cq.from_user
    if not (cq.data and u and isinstance(cq.message, types.Message)):
        await cq.answer(); return
    try:
        _, wday_s, hhmm = cq.data.split(":")
        wday = int(wday_s)
    except Exception:
        await cq.answer(); return

    LAST_WDAY[u.id] = wday
    PENDING[u.id] = (wday, hhmm)

    try: await cq.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    await cq.message.answer("Введите имя ученика:")
    await state.set_state(WeeklyFSM.waiting_name)
    await cq.answer("Ок, ждём имя")

@router.callback_query(F.data.regexp(r"^\d{2}:\d{2}$"))
async def pick_time_fallback(cq: types.CallbackQuery, state: FSMContext):
    u = cq.from_user
    if not (cq.data and u and isinstance(cq.message, types.Message)):
        await cq.answer(); return
    hhmm = cq.data
    wday = LAST_WDAY.get(u.id)

    if wday is None:
        try: await cq.message.edit_reply_markup(reply_markup=None)
        except Exception: pass
        await cq.message.answer("Сначала выберите день недели:", reply_markup=weekdays_kb())
        await cq.answer(); return

    PENDING[u.id] = (wday, hhmm)
    try: await cq.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    await cq.message.answer("Введите имя ученика:")
    await state.set_state(WeeklyFSM.waiting_name)
    await cq.answer("Ок, ждём имя")

@router.message(WeeklyFSM.waiting_name, F.text & ~F.text.startswith("/"))
async def weekly_fill_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя пустое. Введите имя ученика:"); return
    await state.update_data(student_name=name)
    await message.answer("Укажите контакт (почта/телефон):")
    await state.set_state(WeeklyFSM.waiting_contact)

@router.message(WeeklyFSM.waiting_contact, F.text & ~F.text.startswith("/"))
async def weekly_confirm(message: types.Message, state: FSMContext):
    u = message.from_user
    if u is None:
        await message.answer("Не могу определить пользователя Telegram. Попробуйте снова"); return

    contact = (message.text or "").strip()
    if not contact:
        await message.answer("Контакт пустой. Укажите телефон или почту:"); return

    data = await state.get_data()
    if "weekday" in data and "hhmm" in data:
        wday = int(data["weekday"]); hhmm = str(data["hhmm"])
    else:
        pend = PENDING.get(u.id)
        if not pend:
            await state.clear()
            await message.answer("Сессия сброшена. Начните заново: /weekly")
            return
        wday, hhmm = pend

    name = (data.get("student_name") or "Ученик").strip()

    async with SessionLocal() as session:
        busy = await _busy_times_for_weekday(session, wday)
        if hhmm in busy:
            await state.clear(); PENDING.pop(u.id, None)
            await message.answer("Увы, это время уже занято. Попробуйте снова: /weekly")
            return

        user = await BookingService.ensure_user(session, u.id, (u.full_name or ""))
        sub = WeeklySubscription(
            user_id=user.id, student_name=name, student_contact=contact,
            weekday=wday, time_hhmm=hhmm, duration_min=90, is_active=True
        )
        session.add(sub); await session.flush()

        try:
            gcal_id = GoogleCalendarService.create_recurring_event(
                summary=f"Занятие (еженедельное): {name}",
                weekday=wday, time_hhmm=hhmm, duration_min=90,
                attendee_email=contact if ("@" in contact) else None,
                timezone=TZ_NAME,
            )
            if gcal_id: sub.gcal_event_id = gcal_id
        except Exception:
            pass

        await session.commit()

        try: await ReminderService.schedule_for_weekly(get_scheduler(), sub, tz_name=TZ_NAME)
        except Exception: pass

    await state.clear(); PENDING.pop(u.id, None)
    await message.answer(
        f"Еженедельная запись создана\n"
        f"{_weekday_title(wday)} {hhmm}\n"
        f"Имя: {name}\nКонтакт: {contact}"
    )