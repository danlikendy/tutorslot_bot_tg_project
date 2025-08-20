import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import settings
from app.storage.db import engine, Base, SessionLocal
from app.bot.handlers import start as start_handler
from app.bot.handlers import booking as booking_handler
from app.bot.handlers import manage as manage_handler
from app.scheduler.jobs import setup_scheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# aiogram 3.x middleware для DI сессии
from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable

class DBSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]], event, data):
        async with SessionLocal() as session:
            data["session"] = session  # type: AsyncSession
            return await handler(event, data)

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

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # middlewares
    dp.message.middleware(DBSessionMiddleware())
    dp.callback_query.middleware(DBSessionMiddleware())

    # routers
    dp.include_router(start_handler.router)
    dp.include_router(booking_handler.router)
    dp.include_router(manage_handler.router)

    # scheduler
    scheduler = AsyncIOScheduler(timezone=settings.tz)
    setup_scheduler(scheduler, SessionLocal, bot)

    # универсальный текстовый обработчик
    @dp.message()
    async def default_menu(msg):
        text = (msg.text or "").strip()
        if text in ("/start", "Старт", "Menu", "Меню"):
            # НЕ вызываем хэндлер напрямую — повторяем его логику
            from app.services.slot_service import SlotService
            from app.bot.keyboards.common import kb_slots

            async with SessionLocal() as session:
                free = await SlotService.list_free(session)
            await msg.answer("Выберите свободный слот для записи:", reply_markup=kb_slots(free))
            return

        if text == "Мои записи":
            async with SessionLocal() as session:
                await booking_handler.my_bookings(msg, session=session)
            return

        await msg.answer("Доступно: /start, 'Мои записи', /admin (для админов).")

    await on_startup(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")