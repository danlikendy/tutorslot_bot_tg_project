from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from app.services.slot_service import SlotService
from app.bot.keyboards.common import kb_days_with_counts
from app.storage.db import SessionLocal

router = Router(name="start")

@router.message(CommandStart())
async def start(message: Message):
    async with SessionLocal() as session:
        days = await SlotService.available_days(session)
    await message.answer(
        "Выберите день:",
        reply_markup=kb_days_with_counts(list(days.items())),
    )