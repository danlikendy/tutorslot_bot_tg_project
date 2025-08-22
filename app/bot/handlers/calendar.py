from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from app.services.google_calendar_service import create_event

router = Router()

@router.message(Command("book"))
async def book_event(message: types.Message) -> None:
    link = create_event(
        summary="Тестовое событие из бота",
        start_iso="2025-08-22T10:00:00",
        end_iso="2025-08-22T11:00:00",
        timezone="Europe/Moscow",
    )
    if link:
        await message.answer(f"Событие создано\n{link}")
    else:
        await message.answer("Не удалось создать событие в календаре")