from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import os

def parse_admins(value: str) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip()]

class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    # Читаем ADMINS как строку, чтобы не падать на одиночных значениях
    admins_raw: str = Field(default="", alias="ADMINS")
    tz: str = Field(default=os.getenv("TZ", "Europe/Moscow"), alias="TZ")

    # Google Calendar
    google_calendar_enabled: bool = Field(default=False, alias="GOOGLE_CALENDAR_ENABLED")
    google_calendar_id: str = Field(default="primary", alias="GOOGLE_CALENDAR_ID")
    google_credentials_json_path: str = Field(
        default="./google_credentials.json", alias="GOOGLE_CREDENTIALS_JSON_PATH"
    )

    db_url: str = "sqlite+aiosqlite:///./bot.sqlite3"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "populate_by_name": True,
    }

    @property
    def admins(self) -> list[int]:
        # Нормализуем: "123, 456" -> [123, 456]; "123" -> [123]; "" -> []
        return parse_admins(self.admins_raw)

settings = Settings()