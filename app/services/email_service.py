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
            if settings.smtp_port == 465:
                # Для порта 465 используем SSL
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as s:
                    if settings.smtp_user and settings.smtp_password:
                        s.login(settings.smtp_user, settings.smtp_password)
                    s.send_message(msg)
            else:
                # Для других портов используем TLS
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
                    s.starttls()
                    if settings.smtp_user and settings.smtp_password:
                        s.login(settings.smtp_user, settings.smtp_password)
                    s.send_message(msg)
            return True
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.error(f"Failed to send email: {e}")
            return False