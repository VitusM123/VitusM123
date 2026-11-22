"""Adapter: iCal/ICS-Feeds (Veranstaltungskalender von Städten, Museen, Messen, Hochschulen …).

Konfiguration: ``{"url": "https://…/events.ics"}``
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar

from app.core.timeutil import UTC, date_to_utc
from app.providers.activities.base import ActivityCandidate, FetchWindow, GeoPoint, SourceError, get_text
from app.services import recurrence

MAX_PER_SERIES = 30


class ICalFeedSource:
    source_type = "ical"

    def __init__(self, config: dict) -> None:
        if not config.get("url"):
            raise SourceError("URL fehlt")
        self.url = config["url"]

    async def fetch(self, http: httpx.AsyncClient, window: FetchWindow) -> list[ActivityCandidate]:
        text = await get_text(http, self.url.replace("webcal://", "https://", 1))
        try:
            cal = Calendar.from_ical(text)
        except ValueError as exc:
            raise SourceError(f"Kein gültiger iCal-Feed: {exc}") from exc
        tz = ZoneInfo(window.timezone)
        lo = datetime.combine(window.date_from, time.min, tzinfo=tz)
        hi = datetime.combine(window.date_to + timedelta(days=1), time.min, tzinfo=tz)
        result: list[ActivityCandidate] = []
        for comp in cal.walk("VEVENT"):
            if str(comp.get("STATUS", "")).upper() == "CANCELLED" or "DTSTART" not in comp:
                continue
            raw = comp.decoded("DTSTART")
            all_day = not isinstance(raw, datetime)
            start = date_to_utc(raw) if all_day else (raw if raw.tzinfo else raw.replace(tzinfo=tz)).astimezone(UTC)
            if "DTEND" in comp:
                raw_end = comp.decoded("DTEND")
                end = date_to_utc(raw_end) if all_day else (
                    raw_end if raw_end.tzinfo else raw_end.replace(tzinfo=tz)).astimezone(UTC)
            else:
                end = start + (timedelta(days=1) if all_day else timedelta(hours=2))
            spans = [(start, end)]
            if "RRULE" in comp:
                spans = recurrence.expand(
                    start=start, end=end, rrule=comp["RRULE"].to_ical().decode(), all_day=all_day,
                    tz_name=window.timezone, window_start=lo, window_end=hi, display_tz=tz,
                )[:MAX_PER_SERIES]
            geo = comp.get("GEO")
            location = GeoPoint(float(geo.latitude), float(geo.longitude)) if geo is not None else None
            cats = comp.get("CATEGORIES")
            hints = [str(c) for group in (cats if isinstance(cats, list) else [cats] if cats else [])
                     for c in getattr(group, "cats", [group])]
            loc_text = str(comp.get("LOCATION", "")).strip() or None
            for s, e in spans:
                if not (s < hi and e > lo):
                    continue
                result.append(ActivityCandidate(
                    title=str(comp.get("SUMMARY", "")).strip() or "(ohne Titel)",
                    start=s, end=e, all_day=all_day,
                    external_id=f"{comp.get('UID', '')}#{s.isoformat()}",
                    description=str(comp.get("DESCRIPTION", "")).strip() or None,
                    venue=loc_text.split(",")[0] if loc_text else None, address=loc_text,
                    location=location, url=str(comp.get("URL", "")).strip() or None, category_hints=hints,
                ))
        return result
