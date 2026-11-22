"""Adapter: CalDAV (RFC 4791) – für iCloud, funktioniert grundsätzlich auch mit anderen
CalDAV-Servern (Nextcloud, mailbox.org, Radicale …).

- Anmeldung: HTTP Basic (bei iCloud: Apple-ID + app-spezifisches Passwort)
- Erkennung: ``current-user-principal`` → ``calendar-home-set`` → Kalender-Sammlungen
- Delta-Sync: ``sync-collection`` (RFC 6578) + ``calendar-multiget``
- Eine Serie samt geänderten Einzelvorkommen ist **eine** Ressource (.ics mit gleicher UID).
  Einzelvorkommen werden daher immer zusammen mit der Serie geschrieben.
"""
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar as ICal
from icalendar import Event as IEvent
from icalendar import vRecur

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

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav", "cs": "http://calendarserver.org/ns/",
      "ical": "http://apple.com/ns/ical/"}
MEMBERS_PROP = "X-FAMILIENPLANER-MEMBERS"
PRODID = "-//Familienplaner//DE"
MULTIGET_CHUNK = 50


def _q(tag: str) -> str:
    prefix, name = tag.split(":")
    return f"{{{NS[prefix]}}}{name}"


class CalDAVProvider:
    provider_id = "caldav"
    whole_resource = True

    def __init__(self, http: httpx.AsyncClient, base_url: str, username: str, password: str,
                 home_url: str | None = None, default_timezone: str = "Europe/Berlin") -> None:
        self.http = http
        self.base_url = base_url.rstrip("/") + "/"
        self.auth = httpx.BasicAuth(username, password)
        self.home_url = home_url
        self.default_tz = default_timezone
        self._cal_tz: dict[str, str] = {}

    # --- HTTP/XML ---------------------------------------------------------------------------

    async def _dav(self, method: str, url: str, body: str | None = None, depth: str | None = None,
                   headers: dict[str, str] | None = None, ok: tuple[int, ...] = (207,)) -> httpx.Response:
        hdrs = {"Content-Type": "application/xml; charset=utf-8", **(headers or {})}
        if depth is not None:
            hdrs["Depth"] = depth
        try:
            resp = await self.http.request(method, url, content=body, headers=hdrs, auth=self.auth,
                                           follow_redirects=True)
        except httpx.HTTPError as exc:
            raise ProviderError(f"CalDAV-Server nicht erreichbar: {exc}") from exc
        if resp.status_code == 401:
            raise AuthError("Apple-ID oder app-spezifisches Passwort ungültig – bitte neu verbinden")
        if resp.status_code == 404:
            raise RemoteNotFound(url)
        if resp.status_code not in ok:
            raise ProviderError(f"CalDAV {method} {urlparse(url).path}: HTTP {resp.status_code}")
        return resp

    @staticmethod
    def _xml(resp: httpx.Response) -> ET.Element:
        try:
            return ET.fromstring(resp.content)
        except ET.ParseError as exc:
            raise ProviderError(f"Ungültige Server-Antwort: {exc}") from exc

    def _abs(self, href: str, base: str | None = None) -> str:
        return urljoin(base or self.base_url, href)

    async def _propfind_href(self, url: str, prop: str) -> str:
        body = (f'<d:propfind xmlns:d="DAV:" xmlns:c="{NS["c"]}"><d:prop><{prop}/></d:prop></d:propfind>')
        root = self._xml(await self._dav("PROPFIND", url, body, depth="0"))
        el = root.find(f".//{_q(prop)}/{_q('d:href')}")
        if el is None or not (el.text or "").strip():
            raise ProviderError(f"Server liefert kein {prop}")
        return self._abs(el.text.strip(), url)

    async def discover(self) -> str:
        """Ermittelt die Adresse der Kalender-Sammlung des Nutzers."""
        if self.home_url:
            return self.home_url
        principal = await self._propfind_href(self.base_url, "d:current-user-principal")
        self.home_url = await self._propfind_href(principal, "c:calendar-home-set")
        return self.home_url

    # --- Kalender ---------------------------------------------------------------------------

    async def list_calendars(self) -> list[RemoteCalendar]:
        home = await self.discover()
        body = f"""<d:propfind xmlns:d="DAV:" xmlns:c="{NS['c']}" xmlns:cs="{NS['cs']}" xmlns:ical="{NS['ical']}">
          <d:prop><d:resourcetype/><d:displayname/><ical:calendar-color/><c:supported-calendar-component-set/>
          <d:current-user-privilege-set/><c:calendar-timezone/></d:prop></d:propfind>"""
        root = self._xml(await self._dav("PROPFIND", home, body, depth="1"))
        calendars = []
        for resp in root.findall(_q("d:response")):
            href = resp.findtext(_q("d:href"), "").strip()
            prop = self._ok_props(resp)
            if prop is None or prop.find(f"{_q('d:resourcetype')}/{_q('c:calendar')}") is None:
                continue
            comps = prop.find(_q("c:supported-calendar-component-set"))
            if comps is not None and len(comps) and not any(c.get("name") == "VEVENT" for c in comps):
                continue      # z. B. Erinnerungen (VTODO)
            privileges = prop.find(_q("d:current-user-privilege-set"))
            writable = privileges is None or any(
                privileges.find(f".//{_q(p)}") is not None
                for p in ("d:write", "d:write-content", "d:all")
            )
            color = (prop.findtext(_q("ical:calendar-color")) or "").strip()[:7].upper() or None
            url = self._abs(href, home)
            name = (prop.findtext(_q("d:displayname")) or "").strip() or urlparse(url).path.rstrip("/").split("/")[-1]
            calendars.append(RemoteCalendar(remote_id=url, name=name, color=color, read_only=not writable))
        return calendars

    @staticmethod
    def _ok_props(resp: ET.Element) -> ET.Element | None:
        for ps in resp.findall(_q("d:propstat")):
            if " 200 " in (ps.findtext(_q("d:status")) or ""):
                return ps.find(_q("d:prop"))
        return None

    # --- Termine lesen ----------------------------------------------------------------------

    async def fetch_changes(self, calendar_remote_id: str, sync_token: str | None) -> ChangeSet:
        body = f"""<d:sync-collection xmlns:d="DAV:"><d:sync-token>{_xml_escape(sync_token or '')}</d:sync-token>
          <d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>"""
        try:
            resp = await self._dav("REPORT", calendar_remote_id, body, depth="1", ok=(207,))
        except AuthError:
            raise
        except ProviderError as exc:
            if sync_token and any(code in str(exc) for code in ("HTTP 403", "HTTP 409", "HTTP 400")):
                raise SyncTokenExpired(calendar_remote_id) from exc
            if sync_token is None:
                # Server ohne sync-collection (RFC 6578) → vollständige Auflistung per PROPFIND
                log.info("sync-collection nicht unterstützt – Vollabgleich per PROPFIND")
                body = '<d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>'
                resp = await self._dav("PROPFIND", calendar_remote_id, body, depth="1")
            else:
                raise
        root = self._xml(resp)
        changes = ChangeSet(full=sync_token is None)
        changed: list[str] = []
        collection_path = urlparse(calendar_remote_id).path
        for r in root.findall(_q("d:response")):
            href = self._abs(r.findtext(_q("d:href"), "").strip(), calendar_remote_id)
            if urlparse(href).path == collection_path:
                continue
            status = r.findtext(_q("d:status")) or ""
            if " 404 " in status:
                changes.events.append(RemoteEvent(remote_id=href, cancelled=True))
            elif href.endswith(".ics") or self._ok_props(r) is not None:
                changed.append(href)
        changes.next_sync_token = (root.findtext(_q("d:sync-token")) or "").strip() or None

        tz = self._cal_tz.get(calendar_remote_id, self.default_tz)
        for i in range(0, len(changed), MULTIGET_CHUNK):
            for href, etag, data in await self._multiget(calendar_remote_id, changed[i:i + MULTIGET_CHUNK]):
                try:
                    changes.events.extend(parse_resource(href, etag, data, tz))
                except Exception as exc:  # defekte Einträge dürfen den Sync nicht stoppen
                    log.warning("CalDAV-Termin %s übersprungen: %s", href, exc)
        return changes

    async def _multiget(self, calendar_url: str, hrefs: list[str]) -> list[tuple[str, str | None, str]]:
        refs = "".join(f"<d:href>{_xml_escape(urlparse(h).path)}</d:href>" for h in hrefs)
        body = f"""<c:calendar-multiget xmlns:d="DAV:" xmlns:c="{NS['c']}">
          <d:prop><d:getetag/><c:calendar-data/></d:prop>{refs}</c:calendar-multiget>"""
        root = self._xml(await self._dav("REPORT", calendar_url, body, depth="1"))
        result = []
        for r in root.findall(_q("d:response")):
            prop = self._ok_props(r)
            if prop is None:
                continue
            data = prop.findtext(_q("c:calendar-data"))
            if data:
                href = self._abs(r.findtext(_q("d:href"), "").strip(), calendar_url)
                result.append((href, (prop.findtext(_q("d:getetag")) or "").strip() or None, data))
        return result

    # --- Termine schreiben ------------------------------------------------------------------

    async def create_event(self, calendar_remote_id: str, event: OutgoingEvent) -> tuple[str, str | None]:
        event.uid = event.uid or str(uuid.uuid4())
        href = urljoin(calendar_remote_id.rstrip("/") + "/", f"{event.uid}.ics")
        resp = await self._dav("PUT", href, build_ics(event), headers={
            "Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"}, ok=(200, 201, 204))
        return href, resp.headers.get("ETag")

    async def update_event(self, calendar_remote_id: str, remote_id: str, event: OutgoingEvent) -> str | None:
        resp = await self._dav("PUT", remote_id, build_ics(event), headers={
            "Content-Type": "text/calendar; charset=utf-8"}, ok=(200, 201, 204))
        return resp.headers.get("ETag")

    async def delete_event(self, calendar_remote_id: str, remote_id: str) -> None:
        try:
            await self._dav("DELETE", remote_id, ok=(200, 204))
        except RemoteNotFound:
            pass

    def instance_id(self, master_remote_id: str, original_start: datetime, all_day: bool) -> str:
        return f"{master_remote_id}#{_instance_key(original_start, all_day)}"


# --- iCalendar ⇄ Domäne ---------------------------------------------------------------------

def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _instance_key(start: datetime, all_day: bool) -> str:
    return f"{utc_to_date(start):%Y%m%d}" if all_day else f"{start.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def _to_utc(value: date | datetime, fallback_tz: str) -> tuple[datetime, bool]:
    """iCalendar-Wert → (UTC-Zeitpunkt, ganztägig). Schwebende Zeiten gelten als Kalenderzeitzone."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo(fallback_tz))
        return value.astimezone(UTC), False
    return date_to_utc(value), True


def _tzname(value: Any, fallback: str) -> str:
    tz = getattr(value, "tzinfo", None)
    key = getattr(tz, "key", None) or getattr(tz, "zone", None)
    return key if key and key != "UTC" else fallback


def parse_resource(href: str, etag: str | None, data: str, cal_tz: str) -> list[RemoteEvent]:
    """Eine .ics-Ressource → Serie/Einzeltermin plus Einzelvorkommen."""
    cal = ICal.from_ical(data)
    events: list[RemoteEvent] = []
    master_seen = False
    for comp in cal.walk("VEVENT"):
        start_raw = comp.decoded("DTSTART")
        start, all_day = _to_utc(start_raw, cal_tz)
        tz = cal_tz if all_day else _tzname(start_raw, cal_tz)
        if "DTEND" in comp:
            end, _ = _to_utc(comp.decoded("DTEND"), tz)
        elif "DURATION" in comp:
            end = start + comp.decoded("DURATION")
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(0))
        updated = None
        for key in ("LAST-MODIFIED", "DTSTAMP"):
            if key in comp:
                updated, _ = _to_utc(comp.decoded(key), "UTC")
                break
        members = comp.get(MEMBERS_PROP)
        member_ids = [int(x) for x in str(members).split(",") if x.strip().isdigit()] if members is not None else None
        ev = RemoteEvent(
            remote_id=href, etag=etag, uid=str(comp.get("UID", "")) or None,
            cancelled=str(comp.get("STATUS", "")).upper() == "CANCELLED",
            title=str(comp.get("SUMMARY", "")) or "(ohne Titel)",
            description=str(comp["DESCRIPTION"]) if "DESCRIPTION" in comp else None,
            location=str(comp["LOCATION"]) if "LOCATION" in comp else None,
            start=start, end=end, all_day=all_day, timezone=tz, updated=updated,
            member_ids=member_ids,
        )
        if "RECURRENCE-ID" in comp:
            original, _ = _to_utc(comp.decoded("RECURRENCE-ID"), tz)
            ev.recurring_remote_id = href
            ev.original_start = original
            ev.remote_id = f"{href}#{_instance_key(original, all_day)}"
        else:
            master_seen = True
            if "RRULE" in comp:
                ev.rrule = comp["RRULE"].to_ical().decode()
                ev.complete_instances = True
            exdates = comp.get("EXDATE")
            for group in exdates if isinstance(exdates, list) else ([exdates] if exdates is not None else []):
                for item in group.dts:
                    ev.exdates.append(_to_utc(item.dt, tz)[0])
        events.append(ev)
    if not master_seen and events:
        # Nur Einzelvorkommen ohne Serie (selten) → als einzelne Termine behandeln
        for ev in events:
            ev.recurring_remote_id = None
    # Serie zuerst, damit Einzelvorkommen ihr zugeordnet werden können
    return sorted(events, key=lambda e: e.recurring_remote_id is not None)


def _ical_time(value: datetime, all_day: bool, tz: str) -> date | datetime:
    return utc_to_date(value) if all_day else value.astimezone(ZoneInfo(tz))


def _vevent(ev: OutgoingEvent, uid: str, now: datetime) -> IEvent:
    comp = IEvent()
    comp.add("UID", uid)
    comp.add("DTSTAMP", now)
    comp.add("LAST-MODIFIED", now)
    comp.add("SUMMARY", ev.title)
    if ev.description:
        comp.add("DESCRIPTION", ev.description)
    if ev.location:
        comp.add("LOCATION", ev.location)
    comp.add("DTSTART", _ical_time(ev.start, ev.all_day, ev.timezone))
    comp.add("DTEND", _ical_time(ev.end, ev.all_day, ev.timezone))
    comp.add(MEMBERS_PROP, ",".join(str(m) for m in ev.member_ids))
    return comp


def build_ics(ev: OutgoingEvent) -> str:
    """Serie bzw. Einzeltermin samt Einzelvorkommen als iCalendar-Ressource."""
    uid = ev.uid or str(uuid.uuid4())
    now = datetime.now(UTC).replace(microsecond=0)
    cal = ICal()
    cal.add("PRODID", PRODID)
    cal.add("VERSION", "2.0")
    master = _vevent(ev, uid, now)
    if ev.rrule:
        master.add("RRULE", vRecur.from_ical(until_as_date(ev.rrule) if ev.all_day else ev.rrule))
        for ex in sorted(ev.exdates):
            master.add("EXDATE", _ical_time(ex, ev.all_day, ev.timezone))
    cal.add_component(master)
    for inst in ev.instances:
        comp = _vevent(inst, uid, now)
        comp.add("RECURRENCE-ID", _ical_time(inst.original_start, ev.all_day, ev.timezone))
        cal.add_component(comp)
    cal.add_missing_timezones()
    return cal.to_ical().decode()
