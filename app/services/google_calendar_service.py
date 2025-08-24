from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Any, Dict
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import json
import logging

from app.config import settings

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials as UserCreds
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials as SvcCreds

SCOPES = ["https://www.googleapis.com/auth/calendar"]
log = logging.getLogger("gcal")

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_TOKEN_PATH = _ROOT / "integrations" / "token.json"
_DEFAULT_CREDS_PATH = _ROOT / "integrations" / "credentials.json"
_DEFAULT_SA_PATH = _ROOT / "integrations" / "service_account.json"

_TZ_NAME = (getattr(settings, "tz", None) or "UTC").strip() or "UTC"
_TZ = ZoneInfo(_TZ_NAME)

def _ensure_aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=_TZ) if dt.tzinfo is None else dt

def _rfc3339(dt: datetime) -> str:
    return _ensure_aware(dt).isoformat()

def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _fix_user_token_if_needed(token_path: Path, client_secrets_path: Path) -> Dict:
    data = _read_json(token_path)
    need_save = False

    if ("client_id" not in data or "client_secret" not in data) and client_secrets_path.exists():
        cs = _read_json(client_secrets_path)
        installed = cs.get("installed") or cs.get("web") or {}
        if "client_id" in installed and "client_secret" in installed:
            data["client_id"] = installed["client_id"]
            data["client_secret"] = installed["client_secret"]
            need_save = True

    if "scopes" not in data:
        data["scopes"] = SCOPES
        need_save = True

    if need_save:
        token_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return data

class GoogleCalendarService:
    _service: Any = None

    @classmethod
    def _service_oauth(cls):
        token_path = Path((getattr(settings, "google_oauth_token_path", "") or "").strip() or _DEFAULT_TOKEN_PATH)
        creds_path = Path((getattr(settings, "google_credentials_json_path", "") or "").strip() or _DEFAULT_CREDS_PATH)

        if not token_path.exists():
            log.warning("gcal: OAuth token file not found: %s", token_path)
            return None

        try:
            log.info("gcal: using OAuth user token (%s)", token_path)
            data = _fix_user_token_if_needed(token_path, creds_path)

            if not data.get("refresh_token"):
                log.error("gcal: token.json has no refresh_token — пройдите авторизацию заново")
                return None

            creds = UserCreds.from_authorized_user_info(data, scopes=SCOPES)

            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                try:
                    token_path.write_text(creds.to_json(), encoding="utf-8")
                except Exception as e:
                    log.warning("gcal: can't persist refreshed token: %s", e)

            return build("calendar", "v3", credentials=creds)

        except Exception as e:
            log.warning("OAuth creds failed: %s", e)
            return None

    @classmethod
    def _service_service_account(cls):
        sa_path = Path((getattr(settings, "google_credentials_json_path", "") or "").strip() or _DEFAULT_SA_PATH)
        if not sa_path.exists():
            return None
        try:
            creds = SvcCreds.from_service_account_file(str(sa_path), scopes=SCOPES)
            delegate = (getattr(settings, "google_sa_delegate", "") or "").strip()
            if delegate:
                creds = creds.with_subject(delegate)
                log.info("gcal: using Service Account with delegate=%s", delegate)
            else:
                log.info("gcal: using Service Account (%s)", sa_path)
            return build("calendar", "v3", credentials=creds)
        except Exception as e:
            log.warning("ServiceAccount creds failed: %s", e)
            return None

    @classmethod
    def _get_service(cls):
        if not getattr(settings, "google_calendar_enabled", True):
            return None
        if cls._service:
            return cls._service

        svc = cls._service_oauth()
        if not svc and getattr(settings, "google_calendar_allow_service_account", False):
            svc = cls._service_service_account()

        cls._service = svc
        if not svc:
            log.error("gcal: no usable credentials (OAuth token missing/invalid)")
        return svc

    @classmethod
    def _event_body(cls, start_at: datetime, student: str, contact: Optional[str]):
        end_at = _ensure_aware(start_at) + timedelta(minutes=90)

        attendees = []
        if contact and "@" in contact:
            attendees.append({"email": contact})

        return {
            "summary": f"Занятие: {student}",
            "description": f"Ученик: {student}\nКонтакт: {contact or '—'}\n\nЗанятие с репетитором",
            "start": {"dateTime": _rfc3339(start_at), "timeZone": _TZ_NAME},
            "end": {"dateTime": _rfc3339(end_at), "timeZone": _TZ_NAME},
            "attendees": attendees,
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 1440},  # 24 часа
                    {"method": "popup", "minutes": 60},   # 1 час
                ]
            },
            "transparency": "opaque",  # Занято
            "showAs": "busy",
            "colorId": "1",  # Синий цвет для занятий
            "guestsCanModify": False,
            "guestsCanInviteOthers": False,
            "guestsCanSeeOtherGuests": False,
            "sendUpdates": "all",  # Отправляем уведомления всем
        }

    @classmethod
    def create_event(
        cls, booking_id: int, start_at: datetime, student: str, contact: Optional[str]
    ) -> Optional[str]:
        svc = cls._get_service()
        if not svc:
            log.warning("gcal.create: no service available")
            return None
        try:
            log.info(f"Creating event for booking {booking_id}: student={student}, contact={contact}, start_at={start_at}")
            
            body = cls._event_body(start_at, student, contact)
            body["description"] += f"\nBooking #{booking_id}"
            
            log.info(f"Event body prepared: summary={body.get('summary')}, description={body.get('description')}")
            
            # Добавляем настройки для правильной работы с приглашениями
            body["guestsCanModify"] = False
            body["guestsCanInviteOthers"] = False
            body["guestsCanSeeOtherGuests"] = False
            
            # Добавляем настройки для отправки уведомлений
            body["sendUpdates"] = "all"  # Отправляем уведомления всем участникам
            
            # Добавляем уникальный идентификатор для избежания дублирования
            body["source"] = {"title": f"TutorSlot Bot - Booking #{booking_id}", "url": "https://t.me/tutorslot_bot"}
            
            ev = (
                svc.events()
                .insert(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    body=body,
                    sendUpdates="all",  # Дублируем здесь тоже для надежности
                    conferenceDataVersion=1,  # Включаем поддержку конференций
                )
                .execute()
            )
            event_id = ev.get("id")
            if event_id:
                log.info(f"gcal.create: successfully created event {event_id} for booking {booking_id}")
                log.info(f"Event details: summary={ev.get('summary')}, description={ev.get('description')}")
                log.info(f"Event attendees: {ev.get('attendees', [])}")
                log.info(f"Event reminders: {ev.get('reminders', {})}")
                
                # Принудительно обновляем календарь
                cls._force_calendar_refresh(svc)
            else:
                log.error(f"gcal.create: no event ID returned for booking {booking_id}")
            return event_id
        except HttpError as e:
            try:
                detail = json.loads(e.content.decode())
            except Exception:
                detail = str(e)
            log.error("gcal.create error: %s", detail)
            return None
        except Exception as e:
            log.error(f"gcal.create unexpected error: {e}")
            return None

    @classmethod
    def check_calendar_permissions(cls) -> bool:
        """Проверяет права доступа к календарю"""
        svc = cls._get_service()
        if not svc:
            log.error("gcal.check_permissions: no service available")
            return False
        
        try:
            # Пытаемся получить информацию о календаре
            calendar = svc.calendars().get(
                calendarId=getattr(settings, "google_calendar_id", "primary")
            ).execute()
            
            log.info(f"Calendar access confirmed: {calendar.get('summary', 'Unknown')}")
            log.info(f"Calendar permissions: {calendar.get('accessRole', 'Unknown')}")
            
            # Выводим всю информацию о календаре для отладки
            log.info(f"Full calendar info: {json.dumps(calendar, indent=2, default=str)}")
            
            # Проверяем права доступа
            access_role = calendar.get('accessRole', '')
            if access_role in ['owner', 'writer']:
                log.info("Calendar permissions: SUFFICIENT (owner/writer)")
                return True
            elif access_role == 'reader':
                log.error("Calendar permissions: INSUFFICIENT (reader only)")
                return False
            else:
                log.warning(f"Calendar permissions: UNKNOWN ({access_role})")
                log.warning(f"Calendar keys: {list(calendar.keys())}")
                
                # Попробуем проверить права через попытку создания тестового события
                log.info("Trying to test permissions by creating a test event...")
                try:
                    from datetime import datetime, timedelta
                    test_start = datetime.now() + timedelta(hours=1)
                    test_event = {
                        "summary": "Test Permission Event",
                        "start": {"dateTime": test_start.isoformat() + 'Z', "timeZone": "UTC"},
                        "end": {"dateTime": (test_start + timedelta(hours=1)).isoformat() + 'Z', "timeZone": "UTC"},
                    }
                    
                    test_result = svc.events().insert(
                        calendarId=getattr(settings, "google_calendar_id", "primary"),
                        body=test_event,
                        sendUpdates="none"
                    ).execute()
                    
                    if test_result.get('id'):
                        log.info("✅ SUCCESS: Can create events - permissions are SUFFICIENT")
                        # Удаляем тестовое событие
                        svc.events().delete(
                            calendarId=getattr(settings, "google_calendar_id", "primary"),
                            eventId=test_result['id']
                        ).execute()
                        return True
                    else:
                        log.warning("Test event creation failed - no event ID returned")
                        return False
                        
                except Exception as test_e:
                    log.error(f"Test event creation failed: {test_e}")
                    return False
                
        except HttpError as e:
            if e.resp.status == 403:
                log.error("Calendar permissions: ACCESS DENIED (403)")
                return False
            elif e.resp.status == 404:
                log.error("Calendar permissions: CALENDAR NOT FOUND (404)")
                return False
            else:
                log.error(f"Calendar permissions check failed: {e}")
                return False
        except Exception as e:
            log.error(f"Calendar permissions check unexpected error: {e}")
            return False

    @classmethod
    def _force_calendar_refresh(cls, svc):
        """Принудительно обновляет календарь"""
        try:
            # Получаем список событий для принудительного обновления
            now = datetime.now()
            time_min = now.isoformat() + 'Z'
            time_max = (now + timedelta(days=30)).isoformat() + 'Z'
            
            events_result = svc.events().list(
                calendarId=getattr(settings, "google_calendar_id", "primary"),
                timeMin=time_min,
                timeMax=time_max,
                maxResults=10,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            log.info(f"Calendar refreshed, found {len(events_result.get('items', []))} events")
        except Exception as e:
            log.warning(f"Failed to force calendar refresh: {e}")

    @classmethod
    def force_update_event(
        cls, event_id: str, start_at: datetime, student: str, contact: Optional[str], booking_id: int = None
    ) -> Optional[str]:
        """Принудительное обновление события с пересозданием"""
        svc = cls._get_service()
        if not svc or not event_id:
            log.warning("gcal.force_update: no service or event_id")
            return None
        
        try:
            log.info(f"Force updating event {event_id} by recreation")
            
            # Сначала удаляем старое событие
            delete_success = cls.delete_event(event_id)
            if not delete_success:
                log.warning(f"Failed to delete old event {event_id} - may already be deleted")
                # Продолжаем выполнение, так как событие могло быть уже удалено
            
            # Ждем немного для синхронизации
            import time
            time.sleep(2)
            
            # Создаем новое событие с правильным booking_id
            new_event_id = cls.create_event(
                booking_id=booking_id or 999,  # Используем переданный ID или временный
                start_at=start_at,
                student=student,
                contact=contact
            )
            
            if new_event_id:
                log.info(f"Successfully recreated event: {new_event_id}")
                return new_event_id  # Возвращаем новый ID события
            else:
                log.error("Failed to recreate event")
                return None
                
        except Exception as e:
            log.error(f"Force update failed: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
            return None

    @classmethod
    def update_event(
        cls, event_id: str, start_at: datetime, student: str, contact: Optional[str]
    ) -> bool:
        svc = cls._get_service()
        if not svc or not event_id:
            log.warning("gcal.update: no service or event_id")
            return False
        try:
            log.info(f"Starting update for event {event_id}: student={student}, contact={contact}")
            
            # Сначала получаем существующее событие
            existing_event = (
                svc.events()
                .get(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    eventId=event_id,
                )
                .execute()
            )
            
            log.info(f"Retrieved existing event: summary={existing_event.get('summary')}, description={existing_event.get('description')}")
            
            # Создаем новое тело события с обновленными данными
            body = cls._event_body(start_at, student, contact)
            
            log.info(f"New event body: summary={body.get('summary')}, description={body.get('description')}")
            
            # Сохраняем существующие поля которые не должны изменяться
            if "id" in existing_event:
                body["id"] = existing_event["id"]
            if "status" in existing_event:
                body["status"] = existing_event["status"]
            if "created" in existing_event:
                body["created"] = existing_event["created"]
            if "creator" in existing_event:
                body["creator"] = existing_event["creator"]
            if "organizer" in existing_event:
                body["organizer"] = existing_event["organizer"]
            if "htmlLink" in existing_event:
                body["htmlLink"] = existing_event["htmlLink"]
            
            log.info(f"Final event body prepared with preserved fields")
            
            # Используем update для полного обновления события
            (
                svc.events()
                .update(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    eventId=event_id,
                    body=body,
                    sendUpdates="all",
                )
                .execute()
            )
            log.info(f"gcal.update: successfully updated event {event_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                log.error(f"gcal.update: event {event_id} not found")
                return False
            try:
                detail = json.loads(e.content.decode())
            except Exception:
                detail = str(e)
            log.error("gcal.update error: %s", detail)
            return False
        except Exception as e:
            log.error(f"gcal.update unexpected error: {e}")
            return False

    @classmethod
    def delete_event(cls, event_id: str) -> bool:
        svc = cls._get_service()
        if not svc or not event_id:
            log.warning("gcal.delete: no service or event_id")
            return False
        try:
            log.info(f"Deleting event {event_id} with sendUpdates='all'")
            
            (
                svc.events()
                .delete(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    eventId=event_id,
                    sendUpdates="all",  # Отправляем уведомления всем участникам об отмене
                )
                .execute()
            )
            log.info(f"gcal.delete: successfully deleted event {event_id}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                log.warning(f"gcal.delete: event {event_id} not found (already deleted?)")
                return True  # Считаем успехом если событие уже удалено
            try:
                detail = json.loads(e.content.decode())
            except Exception:
                detail = str(e)
            log.error("gcal.delete error: %s", detail)
            return False
        except Exception as e:
            log.error(f"gcal.delete unexpected error: {e}")
            return False

    @classmethod
    def get_event_html_link(cls, event_id: str) -> Optional[str]:
        svc = cls._get_service()
        if not svc or not event_id:
            return None
        try:
            ev = (
                svc.events()
                .get(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    eventId=event_id,
                )
                .execute()
            )
            return ev.get("htmlLink")
        except HttpError as e:
            log.warning("gcal.get_event_html_link error: %s", e)
            return None

    WEEKDAY_TO_BYDAY = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

    @classmethod
    def create_recurring_event(
        cls,
        summary: str,
        weekday: int,
        time_hhmm: str,
        duration_min: int,
        attendee_email: Optional[str],
        timezone: str = _TZ_NAME,
    ) -> Optional[str]:
        svc = cls._get_service()
        if not svc:
            return None

        now = datetime.now(ZoneInfo(timezone))
        days_ahead = (weekday - now.weekday()) % 7
        start_dt = (now + timedelta(days=days_ahead)).replace(
            hour=int(time_hhmm[:2]),
            minute=int(time_hhmm[3:]),
            second=0,
            microsecond=0,
        )
        end_dt = start_dt + timedelta(minutes=duration_min)

        body = {
            "summary": summary,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone},
            "recurrence": [f"RRULE:FREQ=WEEKLY;BYDAY={cls.WEEKDAY_TO_BYDAY[weekday]}"],
        }
        if attendee_email and "@" in attendee_email:
            body["attendees"] = [{"email": attendee_email}]

        try:
            ev = (
                svc.events()
                .insert(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    body=body,
                    sendUpdates="all",
                )
                .execute()
            )
            return ev.get("id")  # master/series id
        except HttpError as e:
            try:
                detail = json.loads(e.content.decode())
            except Exception:
                detail = str(e)
            log.error("gcal.create_recurring error: %s", detail)
            return None

    @classmethod
    def delete_recurring_series(cls, event_id: str) -> bool:
        svc = cls._get_service()
        if not svc or not event_id:
            return False
        try:
            (
                svc.events()
                .delete(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    eventId=event_id,
                    sendUpdates="all",
                )
                .execute()
            )
            return True
        except HttpError as e:
            try:
                detail = json.loads(e.content.decode())
            except Exception:
                detail = str(e)
            log.error("gcal.delete_recurring error: %s", detail)
            return False

def create_event(summary: str, start_iso: str, end_iso: str, timezone: str = "UTC") -> Optional[str]:
    svc = GoogleCalendarService._get_service()
    if not svc:
        return None
    try:
        ev = (
            svc.events()
            .insert(
                calendarId=getattr(settings, "google_calendar_id", "primary"),
                body={
                    "summary": summary,
                    "start": {"dateTime": start_iso, "timeZone": timezone},
                    "end": {"dateTime": end_iso, "timeZone": timezone},
                },
                sendUpdates="all",
            )
            .execute()
        )
        return ev.get("htmlLink")
    except HttpError as e:
        try:
            detail = json.loads(e.content.decode())
        except Exception:
            detail = str(e)
        log.error("gcal.create (simple) error: %s", detail)
        return None