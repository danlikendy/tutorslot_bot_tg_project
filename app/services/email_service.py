from __future__ import annotations
import smtplib
from email.message import EmailMessage
from typing import Optional

from app.config import settings

class EmailService:
    @staticmethod
    def is_email(value: Optional[str]) -> bool:
        if not value:
            return False
        return "@" in value and "." in value

    @staticmethod
    def send(to_email: str, subject: str, body: str) -> bool:
        if not settings.smtp_enabled:
            return False
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
                s.starttls()
                if settings.smtp_user and settings.smtp_password:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
            return True
        except Exception:
            return False