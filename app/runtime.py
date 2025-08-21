from __future__ import annotations
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

_bot: Optional[Bot] = None
_scheduler: Optional[AsyncIOScheduler] = None

def set_bot(b: Bot) -> None:
    global _bot
    _bot = b

def get_bot() -> Bot:
    assert _bot is not None, "Bot is not initialized yet"
    return _bot

def set_scheduler(s: AsyncIOScheduler) -> None:
    global _scheduler
    _scheduler = s

def get_scheduler() -> AsyncIOScheduler:
    assert _scheduler is not None, "Scheduler is not initialized yet"
    return _scheduler