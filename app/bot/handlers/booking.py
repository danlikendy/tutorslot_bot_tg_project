from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.slot_service import SlotService
from app.services.booking_service import BookingService
from app.bot.keyboards.common import kb_slots, kb_my_bookings, kb_reschedule_slots

router = Router(name="booking")

# Простая state-less логика через последовательность сообщений (минимум кода).
# В проде стоит вынести на FSM.

_pending_book = {}      # user_id -> slot_id
_pending_resched = {}   # user_id -> booking_id

@router.callback_query(F.data.startswith("book:"))
async def choose_slot(cb: CallbackQuery, session: AsyncSession):
    slot_id = int(cb.data.split(":")[1])
    _pending_book[cb.from_user.id] = slot_id
    await cb.message.answer("Введите имя ученика:")
    await cb.answer()

@router.message(F.text.as_("student_name"))
async def ask_contact(message: Message, student_name: str, session: AsyncSession):
    if message.from_user.id not in _pending_book:
        return
    # временно сохраняем имя
    _pending_book[(message.from_user.id, "name")] = student_name.strip()
    await message.answer("Укажите контакт (телефон или email):")

@router.message(F.text.as_("contact"))
async def confirm_booking(message: Message, contact: str, session: AsyncSession):
    uid = message.from_user.id
    if uid not in _pending_book:
        return
    slot_id = _pending_book.pop(uid)
    student_name = _pending_book.pop((uid, "name"), message.from_user.full_name or "Ученик")

    user = await BookingService.ensure_user(session, tg_id=uid, name=message.from_user.full_name)
    booking = await BookingService.book(session, user, slot_id, student_name, contact.strip())
    if booking is None:
        await message.answer("Слот уже занят. Выберите другой.", reply_markup=kb_slots(await SlotService.list_free(session)))
        return

    await message.answer(f"✅ Вы записаны: {booking.slot.start_at:%a %d.%m %H:%M}\nИмя: {booking.student_name}\nКонтакт: {booking.student_contact}")

@router.message(F.text == "Мои записи")
async def my_bookings(message: Message, session: AsyncSession):
    user = await BookingService.ensure_user(session, message.from_user.id, message.from_user.full_name)
    bookings = await BookingService.my_bookings(session, user)
    await message.answer("Ваши записи:", reply_markup=kb_my_bookings(bookings))

@router.callback_query(F.data.startswith("cancel:"))
async def cancel(cb: CallbackQuery, session: AsyncSession):
    booking_id = int(cb.data.split(":")[1])
    user = await BookingService.ensure_user(session, cb.from_user.id, cb.from_user.full_name)
    ok = await BookingService.cancel(session, booking_id, user)
    await cb.message.answer("❌ Запись отменена." if ok else "Не удалось отменить запись.")
    await cb.answer()

@router.callback_query(F.data.startswith("reschedule:"))
async def reschedule_pick(cb: CallbackQuery, session: AsyncSession):
    booking_id = int(cb.data.split(":")[1])
    _pending_resched[cb.from_user.id] = booking_id
    free = await SlotService.list_free(session)
    await cb.message.answer("Выберите новый слот:", reply_markup=kb_reschedule_slots(booking_id, free))
    await cb.answer()

@router.callback_query(F.data.startswith("do_reschedule:"))
async def do_reschedule(cb: CallbackQuery, session: AsyncSession):
    _, booking_id, new_slot_id = cb.data.split(":")
    booking_id, new_slot_id = int(booking_id), int(new_slot_id)
    user = await BookingService.ensure_user(session, cb.from_user.id, cb.from_user.full_name)
    b = await BookingService.reschedule(session, booking_id, user, new_slot_id)
    await cb.message.answer("✅ Перенос выполнен." if b else "Не удалось перенести запись.")
    await cb.answer()