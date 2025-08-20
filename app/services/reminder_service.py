from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from app.storage.models import Booking, Slot
from aiogram import Bot

REMIND_24H = timedelta(hours=24)
REMIND_1H = timedelta(hours=1)

class ReminderService:
    @staticmethod
    async def scan_and_notify(session: AsyncSession, bot: Bot) -> None:
        """Периодический сканер: ищет брони с окном T-24h / T-1h и ставит флаги."""
        now = datetime.now()
        res = await session.execute(
            select(Booking).join(Booking.slot).where(Slot.start_at > now - timedelta(hours=1))
        )
        bookings = res.scalars().all()
        for b in bookings:
            start = b.slot.start_at
            dt = start - now

            # t-24h окно
            if not b.remind_24h_sent and timedelta(0) <= dt <= REMIND_24H:
                await bot.send_message(
                    chat_id=b.user.tg_id,
                    text=f"Напоминание (за 24ч): {b.student_name}, занятие {start:%a %d.%m %H:%M}",
                )
                b.remind_24h_sent = True

            # t-1h окно
            if not b.remind_1h_sent and timedelta(0) <= dt <= REMIND_1H:
                await bot.send_message(
                    chat_id=b.user.tg_id,
                    text=f"Напоминание (за 1ч): {b.student_name}, занятие {start:%a %d.%m %H:%M}",
                )
                b.remind_1h_sent = True

        await session.commit()