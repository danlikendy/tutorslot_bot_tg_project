from app.config import settings
from app.services.google_calendar_service import GoogleCalendarService
import logging

log = logging.getLogger(__name__)

class GoogleCalendar:
    enabled = settings.google_calendar_enabled

    @staticmethod
    async def upsert_event(booking_id: int, start_at, student: str, contact: str = None):
        if not GoogleCalendar.enabled:
            return None
        
        try:
            # Создаем новое событие в календаре
            event_id = GoogleCalendarService.create_event(booking_id, start_at, student, contact)
            if event_id:
                log.info(f"Created Google Calendar event: {event_id} for booking {booking_id}")
            return event_id
        except Exception as e:
            log.error(f"Failed to create Google Calendar event: {e}")
            return None

    @staticmethod
    async def delete_event(event_id: str):
        if not GoogleCalendar.enabled:
            return False
        
        try:
            success = GoogleCalendarService.delete_event(event_id)
            if success:
                log.info(f"Deleted Google Calendar event: {event_id}")
            return success
        except Exception as e:
            log.error(f"Failed to delete Google Calendar event: {e}")
            return False

    @staticmethod
    async def update_event(event_id: str, start_at, student: str, contact: str = None):
        if not GoogleCalendar.enabled:
            return False
        
        try:
            success = GoogleCalendarService.update_event(event_id, start_at, student, contact)
            if success:
                log.info(f"Updated Google Calendar event: {event_id}")
            return success
        except Exception as e:
            log.error(f"Failed to update Google Calendar event: {e}")
            return False