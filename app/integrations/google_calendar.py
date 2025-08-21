from app.config import settings

class GoogleCalendar:
    enabled = settings.google_calendar_enabled

    @staticmethod
    async def upsert_event(*_, **__):
        if not GoogleCalendar.enabled:
            return
        # TODO
        return

    @staticmethod
    async def delete_event(*_, **__):
        if not GoogleCalendar.enabled:
            return
        # TODO
        return