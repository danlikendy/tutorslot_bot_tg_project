from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from app.config import settings
from app.services.slot_service import SlotService
from app.bot.keyboards.common import kb_admin, kb_slots

router = Router(name="manage")

def is_admin(user_id: int) -> bool:
    return user_id in settings.admins

@router.message(Command("admin"))
async def admin_panel(message: Message, session: AsyncSession):
    if not is_admin(message.from_user.id):
        await message.answer("Недостаточно прав.")
        return
    free = await SlotService.list_free(session)
    await message.answer("Админ-панель:", reply_markup=kb_admin(len(free)))

@router.callback_query(lambda c: c.data == "admin:free")
async def admin_free(cb, session: AsyncSession):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return
    free = await SlotService.list_free(session)
    await cb.message.answer("Свободные слоты:", reply_markup=kb_slots(free))
    await cb.answer()

@router.callback_query(lambda c: c.data == "admin:add_template")
async def admin_add_template(cb, session: AsyncSession):
    if not is_admin(cb.from_user.id):
        await cb.answer("Нет прав", show_alert=True)
        return
    # шаблон: ближайшая неделя Пн–Пт, слоты 15:00, 17:00, 19:00
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    created = 0
    for d in range(0, 14):  # две недели вперёд
        day = base + timedelta(days=d)
        if day.weekday() >= 5:  # 0-пн ... 6-вс; пропускаем выходные
            continue
        for h in (15, 17, 19):
            start = day.replace(hour=h)
            try:
                await SlotService.add_slot(session, start)
                created += 1
            except Exception:
                pass
    await cb.message.answer(f"Добавлено слотов: {created}")
    await cb.answer()