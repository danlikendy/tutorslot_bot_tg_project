from __future__ import annotations
from aiogram import Router, types
from aiogram.filters import Command


router = Router()


COURSES_TEXT = (
    "Курсы по обществознанию\n\n"
    "📘 ЕГЭ — онлайн-занятия каждую субботу в 12:00. Теория + практика, разбор заданий, проверка ДЗ.\n"
    "👉 [Материалы ЕГЭ](https://disk.yandex.ru/d/1wt4Re2xpEB5eg)\n\n"
    "📘 ОГЭ — онлайн-занятия каждую субботу в 14:00. Пошаговая подготовка, тренировка заданий, обратная связь.\n"
    "👉 [Материалы ОГЭ](https://disk.yandex.ru/d/BOsY8SYYZvrCWg)"
)


@router.message(Command("courses"))
async def courses_info(message: types.Message) -> None:
    await message.answer(COURSES_TEXT, parse_mode="Markdown", disable_web_page_preview=True)