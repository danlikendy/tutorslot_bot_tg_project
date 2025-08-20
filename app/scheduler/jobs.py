from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from app.services.reminder_service import ReminderService

def setup_scheduler(scheduler: AsyncIOScheduler, session_factory, bot: Bot):
    # периодический джоб: каждые 5 минут проверяем напоминания
    async def job():
        async with session_factory() as session:  # type: AsyncSession
            await ReminderService.scan_and_notify(session, bot)

    scheduler.add_job(job, IntervalTrigger(minutes=5), id="reminders", replace_existing=True)
    scheduler.start()