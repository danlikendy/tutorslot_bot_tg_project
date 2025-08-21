"""
Google OAuth

Сценарий:
1) Скрипт печатает ссылку на авторизацию;
2) Перейди по ссылке, выдай доступ;
3) Браузер попытается открыть http://localhost?code=... (это нормально), СКОПИРУЙ значение параметра `code` из адресной строки;
4) Вставь этот код в терминал;
5) Скрипт обменяет code на токены и сохранит token.json.

Переменные окружения (необязательно):
- GOOGLE_OAUTH_CLIENT_FILE — путь к client secrets JSON (если не лежит рядом);
- GOOGLE_OAUTH_TOKEN_FILE  — путь для сохранения token.json (по умолчанию рядом с файлом).
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import sys
from typing import Optional

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as OAuth2Credentials

SCOPES = ["https://www.googleapis.com/auth/calendar"]

THIS_DIR = Path(__file__).resolve().parent
DEFAULT_TOKEN_PATH = THIS_DIR / "token.json"


def _find_client_secrets() -> Path:
    env_path = os.getenv("GOOGLE_OAUTH_CLIENT_FILE")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.exists():
            return p
        print(f"[warn] GOOGLE_OAUTH_CLIENT_FILE задан, но файл не найден: {p}", file=sys.stderr)

    for name in ("credentials.json", "client_secret.json"):
        p = THIS_DIR / name
        if p.exists():
            return p

    raise FileNotFoundError(
        "Не найден файл client secrets. Укажи GOOGLE_OAUTH_CLIENT_FILE "
        f"или положи credentials.json / client_secret.json в {THIS_DIR}"
    )

def _load_existing_creds(token_path: Path) -> Optional[OAuth2Credentials]:
    if not token_path.exists():
        return None
    try:
        return OAuth2Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception as e:
        print(f"[warn] Не удалось прочитать token.json: {e}", file=sys.stderr)
        return None

def _save_creds(creds: OAuth2Credentials, token_path: Path) -> None:
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"[ok] Токен сохранён: {token_path}")

def main() -> None:
    token_path = Path(os.getenv("GOOGLE_OAUTH_TOKEN_FILE", DEFAULT_TOKEN_PATH)).expanduser().resolve()
    client_secrets = _find_client_secrets()

    creds: Optional[OAuth2Credentials] = _load_existing_creds(token_path)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_creds(creds, token_path)
            print("[ok] Существующий токен обновлён")
            return
        except Exception as e:
            print(f"[warn] Не удалось обновить токен: {e}. Переходим к повторной авторизации", file=sys.stderr)

    if not creds or not creds.valid:
        print("[i] Ручной консольный OAuth-флоу (без локального сервера)")

        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
        flow.redirect_uri = "http://localhost"

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

        print("\nОткрой ссылку для авторизации:\n")
        print(auth_url, "\n")
        print("После логина браузер попытается открыть http://localhost?code=... — это нормально")
        print("Скопируй значение параметра 'code' из адресной строки и вставь здесь\n")

        code = input("Вставь code: ").strip()
        flow.fetch_token(code=code)

        creds = OAuth2Credentials.from_authorized_user_info(
            json.loads(flow.credentials.to_json()),
            SCOPES,
        )
        _save_creds(creds, token_path)

    payload = json.loads(creds.to_json())
    has_refresh = bool(payload.get("refresh_token"))
    print("\n[ok] Авторизация завершена")
    print(f"[i] refresh_token: {'есть' if has_refresh else 'нет'}")
    print(f"[i] access_token истекает: {creds.expiry}")

if __name__ == "__main__":
    main()