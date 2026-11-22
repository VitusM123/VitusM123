"""Adapter: RSS-/Atom-Veranstaltungsfeeds.

Termine werden aus Event-Erweiterungen (``ev:startdate``) oder aus dem Text (Titel/Beschreibung,
deutsche Datumsangaben) gelesen. Einträge ohne erkennbares Datum werden übersprungen.

Konfiguration: ``{"url": "https://…/feed.rss"}``
"""
import html
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import feedparser
import httpx

from app.core.timeutil import UTC, date_to_utc
from app.providers.activities.base import ActivityCandidate, FetchWindow, GeoPoint, SourceError, get_text
from app.providers.activities.dateparse import parse_datetime

_TAGS = re.compile(r"<[^>]+>")
# „Vernissage: Licht – 05.12.2026, 19 Uhr“ → Datumsangabe am Titelende entfernen
_TITLE_DATE = re.compile(
    r"\s*[-–|,(]\s*(?:(?:mo|di|mi|do|fr|sa|so)[a-z]*\.?,?\s*)?\d{1,2}\.\s?(?:\d{1,2}\.|[a-zä]+).*$",
    re.IGNORECASE,
)


def strip_date(title: str) -> str:
    stripped = _TITLE_DATE.sub("", title).strip()
    return stripped if len(stripped) >= 3 else title


def clean_html(text: str | None) -> str | None:
    if not text:
        return None
    return " ".join(html.unescape(_TAGS.sub(" ", text)).split()) or None


class RssFeedSource:
    source_type = "rss"

    def __init__(self, config: dict) -> None:
        if not config.get("url"):
            raise SourceError("URL fehlt")
        self.url = config["url"]

    async def fetch(self, http: httpx.AsyncClient, window: FetchWindow) -> list[ActivityCandidate]:
        feed = feedparser.parse(await get_text(http, self.url))
        if feed.bozo and not feed.entries:
            raise SourceError("Kein gültiger RSS-/Atom-Feed")
        tz = ZoneInfo(window.timezone)
        result = []
        for entry in feed.entries:
            title = clean_html(entry.get("title")) or ""
            summary = clean_html(entry.get("summary") or entry.get("description"))
            when = None
            for key in ("ev_startdate", "startdate", "event_startdate"):
                if entry.get(key):
                    try:
                        when = (datetime.fromisoformat(entry[key].replace("Z", "+00:00")), "T" in entry[key])
                    except ValueError:
                        when = parse_datetime(entry[key])
                    break
            if when is None:
                when = parse_datetime(f"{title} {summary or ''}", today=window.date_from)
                if when is not None:
                    title = strip_date(title)
            if when is None:
                continue
            value, has_time = when
            if has_time:
                start = (value if value.tzinfo else value.replace(tzinfo=tz)).astimezone(UTC)
                end, all_day = start + timedelta(hours=2), False
            else:
                start = date_to_utc(value.date())
                end, all_day = start + timedelta(days=1), True
            if not (window.date_from <= start.astimezone(tz).date() <= window.date_to):
                continue
            location = None
            if entry.get("geo_lat") and entry.get("geo_long"):
                location = GeoPoint(float(entry["geo_lat"]), float(entry["geo_long"]))
            place = clean_html(entry.get("ev_location") or entry.get("location"))
            result.append(ActivityCandidate(
                title=title or "(ohne Titel)", start=start, end=end, all_day=all_day,
                external_id=entry.get("id") or entry.get("link"), description=summary,
                venue=place.split(",")[0] if place else None, address=place, location=location,
                url=entry.get("link"), category_hints=[t.get("term", "") for t in entry.get("tags", [])],
            ))
        return result
