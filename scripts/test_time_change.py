#!/usr/bin/env python3
"""
Скрипт для тестирования изменения времени события в Google Calendar
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.google_calendar_service import GoogleCalendarService
from app.config import settings

async def test_time_change():
    """Тестирует изменение времени события в Google Calendar"""
    
    print("Тестирование изменения времени события в Google Calendar")
    print("=" * 60)
    
    # Проверяем настройки
    print(f"Google Calendar включен: {settings.google_calendar_enabled}")
    print(f"Calendar ID: {settings.google_calendar_id}")
    
    if not settings.google_calendar_enabled:
        print("Google Calendar отключен в настройках")
        return
    
    # Создаем событие на 14:00
    print("\n1. Создание события на 14:00...")
    start_at = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
    event_id = GoogleCalendarService.create_event(
        booking_id=999,
        start_at=start_at,
        student="Тестовый ученик",
        contact="test@example.com"
    )
    
    if not event_id:
        print("Не удалось создать событие")
        return
    
    print(f"Событие создано на {start_at.strftime('%d.%m.%Y %H:%M')}: {event_id}")
    
    # Ждем немного
    print("\nОжидание 3 секунд для синхронизации...")
    await asyncio.sleep(3)
    
    # Изменяем время на 16:00
    print("\n2. Изменение времени события с 14:00 на 16:00...")
    new_start_at = start_at.replace(hour=16, minute=0)
    
    print(f"Старое время: {start_at.strftime('%d.%m.%Y %H:%M')}")
    print(f"Новое время: {new_start_at.strftime('%d.%m.%Y %H:%M')}")
    
    new_event_id = GoogleCalendarService.force_update_event(
        event_id=event_id,
        start_at=new_start_at,
        student="Тестовый ученик",
        contact="test@example.com",
        booking_id=999
    )
    
    if new_event_id:
        print("Время события изменено")
        print(f"Новый ID события: {new_event_id}")
        event_id = new_event_id
    else:
        print("Ошибка при изменении времени")
        return
    
    # Ждем немного
    print("\nОжидание 5 секунд для финальной синхронизации...")
    await asyncio.sleep(5)
    
    # Получаем ссылку на событие
    print("\n3. Получение ссылки на обновленное событие...")
    link = GoogleCalendarService.get_event_html_link(event_id)
    if link:
        print(f"Ссылка на событие: {link}")
    else:
        print("Не удалось получить ссылку")
    
    # Удаляем тестовое событие
    print("\n4. Удаление тестового события...")
    success = GoogleCalendarService.delete_event(event_id)
    if success:
        print("Событие удалено")
    else:
        print("Ошибка при удалении события")
    
    print("\nТестирование изменения времени завершено!")
    print("\nТеперь проверьте в Google Calendar:")
    print("   - Событие должно быть на новое время (16:00)")
    print("   - Старое событие (14:00) должно быть удалено")
    print("   - В календаре должно быть только одно событие на 16:00")
    print("\nЕсли видите два события или событие на старом времени:")
    print("   1. Проверьте логи на наличие ошибок")
    print("   2. Убедитесь что у бота есть права на редактирование календаря")
    print("   3. Попробуйте обновить страницу календаря в браузере")

if __name__ == "__main__":
    try:
        asyncio.run(test_time_change())
    except KeyboardInterrupt:
        print("\nТестирование прервано пользователем")
    except Exception as e:
        print(f"Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
