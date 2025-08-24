#!/usr/bin/env python3
"""
Скрипт для тестирования принудительного обновления событий в Google Calendar
"""

import asyncio
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.google_calendar_service import GoogleCalendarService
from app.config import settings

async def test_force_update():
    """Тестирует принудительное обновление событий в Google Calendar"""
    
    print("Тестирование принудительного обновления событий в Google Calendar")
    print("=" * 70)
    
    # Проверяем настройки
    print(f"Google Calendar включен: {settings.google_calendar_enabled}")
    print(f"Calendar ID: {settings.google_calendar_id}")
    
    if not settings.google_calendar_enabled:
        print("Google Calendar отключен в настройках")
        return
    
    # Тестируем создание события
    print("\n1. Создание тестового события...")
    start_at = datetime.now() + timedelta(hours=1)
    event_id = GoogleCalendarService.create_event(
        booking_id=999,
        start_at=start_at,
        student="Тестовый ученик",
        contact="test@example.com"
    )
    
    if not event_id:
        print("Не удалось создать событие")
        return
    
    print(f"Событие создано: {event_id}")
    
    # Ждем немного
    print("\nОжидание 5 секунд для синхронизации...")
    await asyncio.sleep(5)
    
    # Тестируем принудительное обновление (изменение имени)
    print("\n2. Принудительное обновление события (изменение имени)...")
    
    new_event_id = GoogleCalendarService.force_update_event(
        event_id=event_id,
        start_at=start_at,
        student="ОБНОВЛЕННЫЙ УЧЕНИК",
        contact="test@example.com",
        booking_id=999
    )
    
    if new_event_id:
        print("Принудительное обновление выполнено")
        event_id = new_event_id
    else:
        print("Ошибка при принудительном обновлении")
        return
    
    # Ждем немного
    print("\nОжидание 5 секунд для синхронизации...")
    await asyncio.sleep(5)
    
    # Тестируем принудительное обновление (изменение контакта)
    print("\n3. Принудительное обновление события (изменение контакта)...")
    
    new_event_id = GoogleCalendarService.force_update_event(
        event_id=event_id,
        start_at=start_at,
        student="ОБНОВЛЕННЫЙ УЧЕНИК",
        contact="updated@example.com",
        booking_id=999
    )
    
    if new_event_id:
        print("Принудительное обновление выполнено")
        event_id = new_event_id
    else:
        print("Ошибка при принудительном обновлении")
        return
    
    # Ждем немного
    print("\nОжидание 5 секунд для синхронизации...")
    await asyncio.sleep(5)
    
    # Тестируем принудительное обновление (изменение времени)
    print("\n4. Принудительное обновление события (изменение времени)...")
    
    new_start_at = start_at + timedelta(hours=1)
    new_event_id = GoogleCalendarService.force_update_event(
        event_id=event_id,
        start_at=new_start_at,
        student="ОБНОВЛЕННЫЙ УЧЕНИК",
        contact="updated@example.com",
        booking_id=999
    )
    
    if new_event_id:
        print("Принудительное обновление выполнено")
        event_id = new_event_id
    else:
        print("Ошибка при принудительном обновлении")
        return
    
    # Ждем немного
    print("\nОжидание 5 секунд для финальной синхронизации...")
    await asyncio.sleep(5)
    
    # Получаем ссылку на событие
    print("\n5. Получение ссылки на событие...")
    link = GoogleCalendarService.get_event_html_link(event_id)
    if link:
        print(f"Ссылка на событие: {link}")
    else:
        print("Не удалось получить ссылку")
    
    # Удаляем тестовое событие
    print("\n6. Удаление тестового события...")
    success = GoogleCalendarService.delete_event(event_id)
    if success:
        print("Событие удалено")
    else:
        print("Ошибка при удалении события")
    
    print("\nТестирование принудительного обновления завершено!")
    print("\nТеперь проверьте:")
    print("   - В Google Calendar у организатора появились новые события")
    print("   - На email пришли уведомления о создании новых событий")
    print("   - В календаре ученика (если подключен) появились новые события")
    print("   - Старые события были удалены")
    print("\nЕсли изменения все еще не видны:")
    print("   1. Проверьте логи на наличие ошибок")
    print("   2. Убедитесь что у бота есть права на редактирование календаря")
    print("   3. Попробуйте обновить страницу календаря в браузере")
    print("   4. Проверьте что credentials.json и token.json актуальны")

if __name__ == "__main__":
    try:
        asyncio.run(test_force_update())
    except KeyboardInterrupt:
        print("\nТестирование прервано пользователем")
    except Exception as e:
        print(f"Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()
