from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_RUNNING, SchedulerAlreadyRunningError
from sqlalchemy import text

from app.config import settings
from app.storage.db import engine, Base, SessionLocal
from app.bot.handlers import start as start_handler
from app.bot.handlers import booking as booking_handler
from app.bot.handlers import manage as manage_handler
from app.scheduler.jobs import setup_scheduler

from app.runtime import set_bot as rt_set_bot, set_scheduler as rt_set_scheduler
from app.runtime import get_bot as rt_get_bot, get_scheduler as rt_get_scheduler

def get_bot() -> Bot:
    return rt_get_bot()

def get_scheduler() -> AsyncIOScheduler:
    return rt_get_scheduler()

async def on_startup(bot: Bot):
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Записаться на занятие"),
            BotCommand(command="admin", description="Админ-панель"),
        ]
    )

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await conn.execute(text("select 1"))

async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await init_db()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    rt_set_bot(bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start_handler.router)
    dp.include_router(booking_handler.router)
    dp.include_router(manage_handler.router)

    scheduler = AsyncIOScheduler(timezone=settings.tz)
    setup_scheduler(scheduler, SessionLocal, bot)

    if getattr(scheduler, "state", None) != STATE_RUNNING:
        try:
            scheduler.start()
        except SchedulerAlreadyRunningError:
            pass

    rt_set_scheduler(scheduler)

    await on_startup(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")