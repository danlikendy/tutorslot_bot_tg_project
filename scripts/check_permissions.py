#!/usr/bin/env python3
"""
Скрипт для проверки прав доступа к Google Calendar
"""

import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.google_calendar_service import GoogleCalendarService
from app.config import settings

def check_permissions():
    """Проверяет права доступа к Google Calendar"""
    
    print("Проверка прав доступа к Google Calendar")
    print("=" * 50)
    
    # Проверяем настройки
    print(f"Google Calendar включен: {settings.google_calendar_enabled}")
    print(f"Calendar ID: {settings.google_calendar_id}")
    
    if not settings.google_calendar_enabled:
        print("❌ Google Calendar отключен в настройках")
        return False
    
    print("\nПроверяем права доступа...")
    
    # Проверяем права доступа
    has_permissions = GoogleCalendarService.check_calendar_permissions()
    
    if has_permissions:
        print("Права доступа: ДОСТАТОЧНО")
        print("   Бот может создавать, изменять и удалять события")
        return True
    else:
        print("❌ Права доступа: НЕДОСТАТОЧНО")
        print("   Бот не может изменять события в календаре")
        print("\n💡 Решение:")
        print("   1. Убедитесь что credentials.json актуален")
        print("   2. Проверьте что token.json содержит refresh_token")
        print("   3. Убедитесь что у аккаунта есть права owner/writer на календарь")
        print("   4. Попробуйте пересоздать token.json:")
        print("      python -m app.integrations.google_oauth_setup")
        return False

if __name__ == "__main__":
    try:
        success = check_permissions()
        if success:
            print("\nВсе проверки пройдены успешно!")
        else:
            print("\n❌ Обнаружены проблемы с правами доступа")
            sys.exit(1)
    except Exception as e:
        print(f"Ошибка при проверке: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
