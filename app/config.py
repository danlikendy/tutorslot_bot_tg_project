from __future__ import annotations

import os
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

def parse_admins(value: str) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip()]

class Settings(BaseSettings):
    bot_token: str = Field(default="dummy-token", alias="BOT_TOKEN")
    admins_raw: str = Field(default="", alias="ADMINS")
    tz: str = Field(default=os.getenv("TZ", "Europe/Moscow"), alias="TZ")

    booking_mode: str = Field(default="dates", alias="BOOKING_MODE")

    db_url: str = "sqlite+aiosqlite:///./bot.sqlite3"

    reminders_enabled: bool = Field(default=True, alias="REMINDERS_ENABLED")
    remind_offsets_minutes: list[int] = Field(
        default=[1440, 60], alias="REMIND_OFFSETS_MINUTES"
    )

    @field_validator("remind_offsets_minutes", mode="before")
    @classmethod
    def _parse_offsets(cls, v):
        if isinstance(v, (list, tuple)):
            return [int(x) for x in v]
        if v is None or v == "":
            return [1440, 60]
        if isinstance(v, str):
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, (list, tuple)):
                    return [int(x) for x in parsed]
            except Exception:
                return [int(x) for x in v.replace(" ", "").split(",") if x]
        return [int(v)]

    smtp_enabled: bool = Field(default=False, alias="SMTP_ENABLED")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")

    google_calendar_enabled: bool = Field(
        default=False, alias="GOOGLE_CALENDAR_ENABLED"
    )
    google_calendar_id: str = Field(default="primary", alias="GOOGLE_CALENDAR_ID")
    google_credentials_json_path: str = Field(
        default="./google_credentials.json", alias="GOOGLE_CREDENTIALS_JSON_PATH"
    )

    google_oauth_client_secret_path: str = Field(
        default="", alias="GOOGLE_OAUTH_CLIENT_SECRET_PATH"
    )
    google_oauth_token_path: str = Field(
        default="", alias="GOOGLE_OAUTH_TOKEN_PATH"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "populate_by_name": True,
    }

    @property
    def admins(self) -> list[int]:
        return parse_admins(self.admins_raw)

settings = Settings()