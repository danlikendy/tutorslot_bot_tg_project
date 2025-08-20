from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.slot_service import SlotService
from app.bot.keyboards.common import kb_slots

router = Router(name="start")

@router.message(CommandStart())
async def start(message: Message, session: AsyncSession):
    free = await SlotService.list_free(session)
    await message.answer(
        "Выберите свободный слот для записи:",
        reply_markup=kb_slots(free),
    )