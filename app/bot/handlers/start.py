from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from app.services.slot_service import SlotService
from app.bot.keyboards.common import kb_days_with_counts, kb_lesson_types
from app.storage.db import SessionLocal

router = Router(name="start")

@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Выберите тип занятия:",
        reply_markup=kb_lesson_types(),
    )