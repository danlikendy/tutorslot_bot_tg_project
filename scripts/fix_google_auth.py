#!/usr/bin/env python3
"""
Скрипт для исправления проблем с Google аутентификацией
"""

import json
import sys
from pathlib import Path

def fix_google_auth():
    """Исправляет проблемы с Google аутентификацией"""
    
    print("Исправление проблем с Google аутентификацией")
    print("=" * 50)
    
    integrations_dir = Path("app/integrations")
    token_path = integrations_dir / "token.json"
    creds_path = integrations_dir / "credentials.json"
    
    # Проверяем наличие файлов
    print(f"Проверяем файлы аутентификации...")
    print(f"Token file: {'OK' if token_path.exists() else 'MISSING'} {token_path}")
    print(f"Credentials file: {'OK' if creds_path.exists() else 'MISSING'} {creds_path}")
    
    if not token_path.exists():
        print("\nФайл token.json не найден!")
        print("Решение: Запустите python -m app.integrations.google_oauth_setup")
        return False
    
    if not creds_path.exists():
        print("\nФАЙЛ CREDENTIALS.JSON ОТСУТСТВУЕТ!")
        print("Это критическая проблема!")
        print("\nРешение:")
        print("1. Скачайте credentials.json из Google Cloud Console:")
        print("   - Перейдите в https://console.cloud.google.com/")
        print("   - Выберите ваш проект")
        print("   - Перейдите в 'APIs & Services' > 'Credentials'")
        print("   - Скачайте OAuth 2.0 Client ID (тип: Desktop application)")
        print("   - Переименуйте в credentials.json")
        print("   - Поместите в папку app/integrations/")
        print("\n2. После этого запустите:")
        print("   python -m app.integrations.google_oauth_setup")
        return False
    
    # Проверяем содержимое token.json
    try:
        with open(token_path, 'r', encoding='utf-8') as f:
            token_data = json.load(f)
        
        print(f"\nПроверяем содержимое token.json...")
        print(f"Client ID: {'OK' if 'client_id' in token_data else 'MISSING'}")
        print(f"Client Secret: {'OK' if 'client_secret' in token_data else 'MISSING'}")
        print(f"Refresh Token: {'OK' if 'refresh_token' in token_data else 'MISSING'}")
        print(f"Scopes: {'OK' if 'scopes' in token_data else 'MISSING'}")
        
        if 'refresh_token' not in token_data:
            print("\nВ token.json отсутствует refresh_token!")
            print("Решение: Пересоздайте токен через OAuth setup")
            return False
            
        print("\nToken.json выглядит корректно")
        
    except Exception as e:
        print(f"\nОшибка при чтении token.json: {e}")
        return False
    
    # Проверяем содержимое credentials.json
    try:
        with open(creds_path, 'r', encoding='utf-8') as f:
            creds_data = json.load(f)
        
        print(f"\nПроверяем содержимое credentials.json...")
        
        if 'installed' in creds_data:
            installed = creds_data['installed']
            print(f"Client ID: {'OK' if 'client_id' in installed else 'MISSING'}")
            print(f"Client Secret: {'OK' if 'client_secret' in installed else 'MISSING'}")
            print(f"Auth URI: {'OK' if 'auth_uri' in installed else 'MISSING'}")
            print(f"Token URI: {'OK' if 'token_uri' in installed else 'MISSING'}")
        elif 'web' in creds_data:
            web = creds_data['web']
            print(f"Client ID: {'OK' if 'client_id' in web else 'MISSING'}")
            print(f"Client Secret: {'OK' if 'client_secret' in web else 'MISSING'}")
            print(f"Auth URI: {'OK' if 'auth_uri' in web else 'MISSING'}")
            print(f"Token URI: {'OK' if 'token_uri' in web else 'MISSING'}")
        else:
            print("Неизвестный формат credentials.json")
            return False
            
        print("\nCredentials.json выглядит корректно")
        
    except Exception as e:
        print(f"\nОшибка при чтении credentials.json: {e}")
        return False
    
    print("\nВсе файлы аутентификации в порядке!")
    print("Теперь можно запустить:")
    print("   python scripts/check_permissions.py")
    
    return True

if __name__ == "__main__":
    try:
        success = fix_google_auth()
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"Ошибка при проверке: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
