"""Adapter: Google Calendar API v3.

Anmeldung: OAuth 2.0 „Desktop-App“-Client mit Loopback-Weiterleitung und PKCE.
(Der Device Flow für TV-Geräte unterstützt keine Kalender-Berechtigungen.)

- Auf dem Pi selbst leitet Google nach der Anmeldung direkt an
  ``http://127.0.0.1:<port>/api/accounts/google/callback`` zurück.
- Auf Handy/Laptop schlägt diese Weiterleitung fehl; die Adresse aus der Adresszeile wird
  dann in die Einstellungen kopiert und der Code daraus gelesen.

Delta-Sync: ``events.list`` mit ``syncToken``; HTTP 410 erzwingt einen Voll-Sync.
Die Zuordnung zu Familienmitgliedern wird in ``extendedProperties.private`` gespeichert.
"""
import base64
import hashlib
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse
from zoneinfo import ZoneInfo

import httpx

from app.core.timeutil import UTC, date_to_utc, utc_to_date
from app.providers.calendar.base import (
    AuthError,
    ChangeSet,
    OutgoingEvent,
    ProviderError,
    RemoteCalendar,
    RemoteEvent,
    RemoteNotFound,
    SyncTokenExpired,
)
from app.services.recurrence import until_as_date

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",   # Kalenderliste
    "https://www.googleapis.com/auth/calendar.events",     # Termine lesen/schreiben
]
MEMBERS_KEY = "familienplaner_members"
READ_ONLY_ROLES = {"reader", "freeBusyReader"}


# --- OAuth ----------------------------------------------------------------------------------

def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(client_id: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",     # Refresh-Token anfordern
        "prompt": "consent",          # Refresh-Token auch bei erneuter Verbindung
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params, quote_via=quote)}"


def parse_redirect(url_or_code: str) -> tuple[str, str | None]:
    """Liest ``code`` und ``state`` aus der kopierten Weiterleitungsadresse (oder nimmt einen reinen Code)."""
    text = url_or_code.strip()
    if "code=" not in text and "error=" not in text:
        return text, None
    query = parse_qs(urlparse(text).query or text.split("?", 1)[-1])
    if "error" in query:
        raise AuthError(f"Google hat die Anmeldung abgelehnt: {query['error'][0]}")
    if "code" not in query:
        raise AuthError("In der Adresse wurde kein Anmeldecode gefunden")
    return query["code"][0], (query.get("state") or [None])[0]


def _token_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        return data.get("error_description") or data.get("error") or resp.text
    except ValueError:
        return resp.text


async def exchange_code(http: httpx.AsyncClient, client_id: str, client_secret: str, code: str,
                        redirect_uri: str, code_verifier: str) -> dict[str, Any]:
    resp = await http.post(TOKEN_URL, data={
        "client_id": client_id, "client_secret": client_secret, "code": code,
        "code_verifier": code_verifier, "grant_type": "authorization_code", "redirect_uri": redirect_uri,
    })
    if resp.status_code != 200:
        raise AuthError(f"Anmeldecode ungültig: {_token_error(resp)}")
    data = resp.json()
    if "refresh_token" not in data:
        raise AuthError("Google hat kein Refresh-Token geliefert – bitte Zugriff in Google entfernen und neu verbinden")
    return _credentials_from_token(data)


def _credentials_from_token(data: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    creds = dict(previous or {})
    creds.update({
        "access_token": data["access_token"],
        "expires_at": time.time() + int(data.get("expires_in", 3600)) - 60,
        "scope": data.get("scope", creds.get("scope")),
    })
    if data.get("refresh_token"):
        creds["refresh_token"] = data["refresh_token"]
    return creds


# --- Provider -------------------------------------------------------------------------------

class GoogleCalendarProvider:
    provider_id = "google"
    whole_resource = False

    def __init__(
        self,
        http: httpx.AsyncClient,
        credentials: dict[str, Any],
        client_id: str,
        client_secret: str,
        on_credentials: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
        default_timezone: str = "Europe/Berlin",
    ) -> None:
        self.http = http
        self.creds = credentials
        self.client_id = client_id
        self.client_secret = client_secret
        self.on_credentials = on_credentials
        self.default_tz = default_timezone
        self._cal_tz: dict[str, str] = {}

    # Authentifizierung
    async def _token(self, force_refresh: bool = False) -> str:
        if force_refresh or not self.creds.get("access_token") or time.time() >= self.creds.get("expires_at", 0):
            await self._refresh()
        return self.creds["access_token"]

    async def _refresh(self) -> None:
        if not self.creds.get("refresh_token"):
            raise AuthError("Kein Refresh-Token vorhanden – bitte Google-Konto neu verbinden")
        resp = await self.http.post(TOKEN_URL, data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": self.creds["refresh_token"], "grant_type": "refresh_token",
        })
        if resp.status_code in (400, 401):
            raise AuthError(f"Google-Anmeldung abgelaufen – bitte neu verbinden ({_token_error(resp)})")
        if resp.status_code != 200:
            raise ProviderError(f"Token-Erneuerung fehlgeschlagen: HTTP {resp.status_code}")
        self.creds = _credentials_from_token(resp.json(), self.creds)
        if self.on_credentials:
            result = self.on_credentials(self.creds)
            if result is not None:
                await result

    async def _request(self, method: str, path: str, *, params: dict | None = None,
                       json: dict | None = None) -> httpx.Response:
        url = f"{API}{path}"
        for attempt in range(2):
            token = await self._token(force_refresh=attempt > 0)
            resp = await self.http.request(method, url, params=params, json=json,
                                           headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 401 and attempt == 0:
                continue  # Token abgelaufen/widerrufen → einmal erneuern
            break
        if resp.status_code == 401:
            raise AuthError("Google lehnt die Zugangsdaten ab – bitte neu verbinden")
        if resp.status_code == 404:
            raise RemoteNotFound(path)
        if resp.status_code >= 400 and not (resp.status_code == 410 and method == "GET"):
            raise ProviderError(f"Google-API {method} {path}: HTTP {resp.status_code} {resp.text[:200]}")
        return resp

    # Kalender
    async def list_calendars(self) -> list[RemoteCalendar]:
        calendars: list[RemoteCalendar] = []
        page: str | None = None
        while True:
            params = {"maxResults": 250, **({"pageToken": page} if page else {})}
            data = (await self._request("GET", "/users/me/calendarList", params=params)).json()
            for item in data.get("items", []):
                if item.get("deleted"):
                    continue
                cal = RemoteCalendar(
                    remote_id=item["id"],
                    name=item.get("summaryOverride") or item.get("summary") or item["id"],
                    color=(item.get("backgroundColor") or "").upper() or None,
                    read_only=item.get("accessRole") in READ_ONLY_ROLES,
                    primary=bool(item.get("primary")),
                    selected=bool(item.get("selected", True)),
                    timezone=item.get("timeZone"),
                )
                if cal.timezone:
                    self._cal_tz[cal.remote_id] = cal.timezone
                calendars.append(cal)
            page = data.get("nextPageToken")
            if not page:
                return calendars

    # Termine
    async def fetch_changes(self, calendar_remote_id: str, sync_token: str | None) -> ChangeSet:
        changes = ChangeSet(full=sync_token is None)
        page: str | None = None
        cal_tz = self._cal_tz.get(calendar_remote_id, self.default_tz)
        while True:
            params: dict[str, Any] = {"maxResults": 250, "showDeleted": "true", "singleEvents": "false"}
            if sync_token:
                params["syncToken"] = sync_token
            if page:
                params["pageToken"] = page
            resp = await self._request("GET", f"/calendars/{quote(calendar_remote_id, safe='')}/events", params=params)
            if resp.status_code == 410:
                raise SyncTokenExpired(calendar_remote_id)
            data = resp.json()
            cal_tz = data.get("timeZone") or cal_tz
            for item in data.get("items", []):
                try:
                    changes.events.append(parse_event(item, cal_tz))
                except (KeyError, ValueError) as exc:
                    log.warning("Google-Termin %s übersprungen: %s", item.get("id"), exc)
            page = data.get("nextPageToken")
            if not page:
                changes.next_sync_token = data.get("nextSyncToken")
                return changes

    async def create_event(self, calendar_remote_id: str, event: OutgoingEvent) -> tuple[str, str | None]:
        resp = await self._request("POST", f"/calendars/{quote(calendar_remote_id, safe='')}/events",
                                   json=to_google(event))
        data = resp.json()
        return data["id"], data.get("etag")

    async def update_event(self, calendar_remote_id: str, remote_id: str, event: OutgoingEvent) -> str | None:
        path = f"/calendars/{quote(calendar_remote_id, safe='')}/events/{quote(remote_id, safe='')}"
        resp = await self._request("PUT", path, json=to_google(event))
        return resp.json().get("etag")

    async def delete_event(self, calendar_remote_id: str, remote_id: str) -> None:
        path = f"/calendars/{quote(calendar_remote_id, safe='')}/events/{quote(remote_id, safe='')}"
        try:
            await self._request("DELETE", path)
        except RemoteNotFound:
            pass
        except ProviderError as exc:
            if "HTTP 410" not in str(exc):   # bereits gelöscht
                raise

    def instance_id(self, master_remote_id: str, original_start: datetime, all_day: bool) -> str:
        if all_day:
            return f"{master_remote_id}_{utc_to_date(original_start):%Y%m%d}"
        return f"{master_remote_id}_{original_start.astimezone(UTC):%Y%m%dT%H%M%SZ}"


# --- Abbildung Google ⇄ Domäne --------------------------------------------------------------

def _parse_time(obj: dict[str, Any], fallback_tz: str) -> tuple[datetime, bool, str]:
    """Google-Zeitobjekt → (UTC-Zeitpunkt, ganztägig, Zeitzone)."""
    tz = obj.get("timeZone") or fallback_tz
    if "date" in obj:
        return date_to_utc(date.fromisoformat(obj["date"])), True, tz
    value = datetime.fromisoformat(obj["dateTime"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(tz))
    return value.astimezone(UTC), False, tz


def _parse_exdate_line(line: str, event_tz: str) -> list[datetime]:
    head, _, values = line.partition(":")
    params = dict(p.split("=", 1) for p in head.split(";")[1:] if "=" in p)
    tz = ZoneInfo(params.get("TZID", event_tz))
    result = []
    for raw in values.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if len(raw) == 8:                                        # YYYYMMDD
            result.append(date_to_utc(datetime.strptime(raw, "%Y%m%d").date()))
        elif raw.endswith("Z"):
            result.append(datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC))
        else:
            result.append(datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=tz).astimezone(UTC))
    return result


def parse_event(item: dict[str, Any], cal_tz: str) -> RemoteEvent:
    ev = RemoteEvent(
        remote_id=item["id"],
        etag=item.get("etag"),
        cancelled=item.get("status") == "cancelled",
        title=item.get("summary") or "(ohne Titel)",
        description=item.get("description"),
        location=item.get("location"),
        recurring_remote_id=item.get("recurringEventId"),
    )
    if item.get("updated"):
        ev.updated = datetime.fromisoformat(item["updated"].replace("Z", "+00:00"))
    if "start" in item and "end" in item:
        ev.start, ev.all_day, ev.timezone = _parse_time(item["start"], cal_tz)
        ev.end, _, _ = _parse_time(item["end"], cal_tz)
    if item.get("originalStartTime"):
        ev.original_start, all_day, _ = _parse_time(item["originalStartTime"], cal_tz)
        ev.all_day = ev.all_day or all_day
    for line in item.get("recurrence", []):
        upper = line.upper()
        if upper.startswith("RRULE:"):
            ev.rrule = line[6:]
        elif upper.startswith("EXDATE"):
            ev.exdates.extend(_parse_exdate_line(line, ev.timezone or cal_tz))
        else:
            log.info("Wiederholungsangabe nicht unterstützt und ignoriert: %s", line)
    members = item.get("extendedProperties", {}).get("private", {}).get(MEMBERS_KEY)
    if members is not None:
        ev.member_ids = [int(x) for x in members.split(",") if x.strip().isdigit()]
    return ev


def _google_time(value: datetime, all_day: bool, tz: str) -> dict[str, str]:
    if all_day:
        return {"date": utc_to_date(value).isoformat()}
    return {"dateTime": value.astimezone(ZoneInfo(tz)).isoformat(), "timeZone": tz}


def to_google(ev: OutgoingEvent) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": ev.title,
        "description": ev.description or "",
        "location": ev.location or "",
        "start": _google_time(ev.start, ev.all_day, ev.timezone),
        "end": _google_time(ev.end, ev.all_day, ev.timezone),
        "extendedProperties": {"private": {MEMBERS_KEY: ",".join(str(m) for m in ev.member_ids)}},
    }
    if ev.rrule:
        lines = [f"RRULE:{until_as_date(ev.rrule) if ev.all_day else ev.rrule}"]
        for ex in sorted(ev.exdates):
            if ev.all_day:
                lines.append(f"EXDATE;VALUE=DATE:{utc_to_date(ex):%Y%m%d}")
            else:
                lines.append(f"EXDATE;TZID={ev.timezone}:{ex.astimezone(ZoneInfo(ev.timezone)):%Y%m%dT%H%M%S}")
        body["recurrence"] = lines
    if ev.recurring_remote_id and ev.original_start:
        body["recurringEventId"] = ev.recurring_remote_id
        body["originalStartTime"] = _google_time(ev.original_start, ev.all_day, ev.timezone)
    return body
