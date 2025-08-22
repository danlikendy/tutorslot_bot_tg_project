# app/main.py
from __future__ import annotations

import asyncio, logging, sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_RUNNING, SchedulerAlreadyRunningError
from sqlalchemy import text

from app.config import settings
from app.storage.db import engine, Base, SessionLocal
from app.scheduler.jobs import setup_scheduler

from app.bot.handlers import start, courses, calendar, booking, weekly_ui, manage

from app.runtime import (
    set_bot as rt_set_bot, set_scheduler as rt_set_scheduler,
    get_bot as rt_get_bot, get_scheduler as rt_get_scheduler,
)

def get_bot() -> Bot: return rt_get_bot()
def get_scheduler() -> AsyncIOScheduler: return rt_get_scheduler()

async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start",        description="Записаться на занятие"),
            BotCommand(command="my",           description="Мои записи"),
            # BotCommand(command="weekly",       description="Еженедельная запись"),
            # BotCommand(command="weekly_list",  description="Мои еженедельные записи"),
            # BotCommand(command="weekly_del",   description="Удалить еженедельную запись"),
            BotCommand(command="courses",      description="Курсы: информация и ссылки"),
            BotCommand(command="admin",        description="Админ‑панель"),
        ],
        scope=BotCommandScopeDefault(),
    )

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await conn.execute(text("select 1"))

async def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await init_db()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    rt_set_bot(bot)

    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(courses.router)
    dp.include_router(calendar.router)
    dp.include_router(booking.router)
    # dp.include_router(weekly_ui.router)
    dp.include_router(manage.router)

    scheduler = AsyncIOScheduler(timezone=settings.tz)
    setup_scheduler(scheduler, SessionLocal, bot)
    if getattr(scheduler, "state", None) != STATE_RUNNING:
        try:
            scheduler.start()
        except SchedulerAlreadyRunningError:
            pass
    rt_set_scheduler(scheduler)

    await _set_commands(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")