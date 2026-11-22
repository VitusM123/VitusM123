"""Adapter: Veranstaltungsseiten ohne Feed – Auslesen per CSS-Selektoren.

Konfiguration::

    {"url": "https://www.example.de/veranstaltungen",
     "item": ".event",          # ein Element je Veranstaltung
     "title": "h3",             # relativ zum Element
     "date": ".date",           # Text mit Datum/Uhrzeit (deutsche Formate)
     "link": "a",               # optional (href)
     "location": ".ort",        # optional
     "description": ".teaser"}  # optional

Bitte Nutzungsbedingungen und robots.txt der Seite beachten. Abgerufen wird nur selten
(Standard: alle 12 Stunden), wie bei einem normalen Besuch.
"""
from datetime import timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.core.timeutil import UTC, date_to_utc
from app.providers.activities.base import ActivityCandidate, FetchWindow, SourceError, get_text
from app.providers.activities.dateparse import parse_datetime

MAX_ITEMS = 300


class ScraperSource:
    source_type = "scraper"

    def __init__(self, config: dict) -> None:
        missing = [k for k in ("url", "item", "title", "date") if not config.get(k)]
        if missing:
            raise SourceError(f"Angaben fehlen: {', '.join(missing)}")
        self.cfg = config

    async def fetch(self, http: httpx.AsyncClient, window: FetchWindow) -> list[ActivityCandidate]:
        tree = LexborHTMLParser(await get_text(http, self.cfg["url"]))
        tz = ZoneInfo(window.timezone)
        items = tree.css(self.cfg["item"])[:MAX_ITEMS]
        if not items:
            raise SourceError(f"Keine Elemente für Selektor „{self.cfg['item']}“ gefunden")
        result = []
        for node in items:
            def text(selector: str | None, node=node) -> str | None:
                if not selector:
                    return None
                el = node.css_first(selector)
                return " ".join(el.text(separator=" ").split()) if el else None

            title = text(self.cfg["title"])
            when = parse_datetime(text(self.cfg["date"]) or "", today=window.date_from)
            if not title or when is None:
                continue
            value, has_time = when
            if has_time:
                start = value.replace(tzinfo=tz).astimezone(UTC)
                end, all_day = start + timedelta(hours=2), False
            else:
                start = date_to_utc(value.date())
                end, all_day = start + timedelta(days=1), True
            if not (window.date_from <= value.date() <= window.date_to):
                continue
            link = None
            if self.cfg.get("link"):
                a = node.css_first(self.cfg["link"])
                if a and a.attributes.get("href"):
                    link = urljoin(self.cfg["url"], a.attributes["href"])
            place = text(self.cfg.get("location"))
            result.append(ActivityCandidate(
                title=title, start=start, end=end, all_day=all_day, external_id=link or f"{title}|{value}",
                description=text(self.cfg.get("description")), venue=place.split(",")[0] if place else None,
                address=place, url=link,
            ))
        return result
