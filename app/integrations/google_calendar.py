# Заглушка под Google Calendar; боевую интеграцию подключим после получения creds.
# Идея: на create/cancel/reschedule вызывать upsert/delete события в календаре.

from app.config import settings

class GoogleCalendar:
    enabled = settings.google_calendar_enabled

    @staticmethod
    async def upsert_event(*_, **__):
        if not GoogleCalendar.enabled:
            return
        # TODO: реализовать через googleapiclient.discovery.build("calendar","v3", credentials=...)
        return

    @staticmethod
    async def delete_event(*_, **__):
        if not GoogleCalendar.enabled:
            return
        # TODO
        return