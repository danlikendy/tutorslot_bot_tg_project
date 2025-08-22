# app/bot/handlers/courses.py
from __future__ import annotations
from aiogram import Router, types
from aiogram.filters import Command

router = Router()

COURSES_TEXT = (
    "<b>Курсы</b>\n\n"
    "— ОГЭ по обществознанию — вт/чт 17:00–18:30\n"
    "Материалы: https://disk.yandex.ru/i/oge-link\n\n"
    "— ЕГЭ по обществознанию — пн/ср 19:00–20:30\n"
    "Материалы: https://disk.yandex.ru/i/ege-link\n"
)

@router.message(Command("courses"))
async def courses_info(message: types.Message) -> None:
    await message.answer(COURSES_TEXT, disable_web_page_preview=True)