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
            "description": f"Ученик: {student}\nКонтакт: {contact or '—'}",
            "start": {"dateTime": _rfc3339(start_at), "timeZone": _TZ_NAME},
            "end": {"dateTime": _rfc3339(end_at), "timeZone": _TZ_NAME},
            "attendees": attendees,
        }

    @classmethod
    def create_event(
        cls, booking_id: int, start_at: datetime, student: str, contact: Optional[str]
    ) -> Optional[str]:
        svc = cls._get_service()
        if not svc:
            return None
        try:
            body = cls._event_body(start_at, student, contact)
            body["description"] += f"\nBooking #{booking_id}"
            ev = (
                svc.events()
                .insert(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    body=body,
                    sendUpdates="all",
                )
                .execute()
            )
            return ev.get("id")
        except HttpError as e:
            try:
                detail = json.loads(e.content.decode())
            except Exception:
                detail = str(e)
            log.error("gcal.create error: %s", detail)
            return None

    @classmethod
    def update_event(
        cls, event_id: str, start_at: datetime, student: str, contact: Optional[str]
    ) -> bool:
        svc = cls._get_service()
        if not svc or not event_id:
            return False
        try:
            body = cls._event_body(start_at, student, contact)
            (
                svc.events()
                .patch(
                    calendarId=getattr(settings, "google_calendar_id", "primary"),
                    eventId=event_id,
                    body=body,
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
            log.error("gcal.update error: %s", detail)
            return False

    @classmethod
    def delete_event(cls, event_id: str) -> bool:
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
            log.error("gcal.delete error: %s", detail)
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