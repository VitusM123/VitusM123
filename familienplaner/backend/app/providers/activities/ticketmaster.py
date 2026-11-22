"""Adapter: Ticketmaster Discovery API (Konzerte, Shows, Sport, Familie – mit Umkreissuche).

Kostenloser API-Schlüssel: https://developer.ticketmaster.com (Kontingent 5000 Abrufe/Tag).
Konfiguration: ``{"api_key": "…"}`` (wird verschlüsselt gespeichert)
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.core.timeutil import UTC, date_to_utc
from app.providers.activities.base import ActivityCandidate, FetchWindow, GeoPoint, SourceError

API_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
MAX_PAGES = 3


class TicketmasterSource:
    source_type = "ticketmaster"

    def __init__(self, config: dict) -> None:
        if not config.get("api_key"):
            raise SourceError("API-Schlüssel fehlt")
        self.api_key = config["api_key"]

    async def fetch(self, http: httpx.AsyncClient, window: FetchWindow) -> list[ActivityCandidate]:
        if window.center is None:
            raise SourceError("Für Ticketmaster bitte zuerst den Wohnort festlegen")
        tz = ZoneInfo(window.timezone)
        start = datetime.combine(window.date_from, time.min, tzinfo=tz).astimezone(UTC)
        end = datetime.combine(window.date_to, time.max.replace(microsecond=0), tzinfo=tz).astimezone(UTC)
        result: list[ActivityCandidate] = []
        for page in range(MAX_PAGES):
            try:
                resp = await http.get(API_URL, params={
                    "apikey": self.api_key, "latlong": f"{window.center.lat:.4f},{window.center.lon:.4f}",
                    "radius": int(min(window.radius_km, 300)), "unit": "km", "size": 100, "page": page,
                    "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "sort": "date,asc", "locale": "*",
                })
            except httpx.HTTPError as exc:
                raise SourceError(f"Ticketmaster nicht erreichbar: {exc}") from exc
            if resp.status_code == 401:
                raise SourceError("Ticketmaster: API-Schlüssel ungültig")
            if resp.status_code != 200:
                raise SourceError(f"Ticketmaster antwortet mit HTTP {resp.status_code}")
            data = resp.json()
            for ev in data.get("_embedded", {}).get("events", []):
                cand = _parse(ev, tz)
                if cand:
                    result.append(cand)
            info = data.get("page", {})
            if info.get("number", 0) + 1 >= info.get("totalPages", 0):
                break
        return result


def _parse(ev: dict, tz: ZoneInfo) -> ActivityCandidate | None:
    start_info = ev.get("dates", {}).get("start", {})
    if start_info.get("dateTime"):
        start = datetime.fromisoformat(start_info["dateTime"].replace("Z", "+00:00"))
        end, all_day = start + timedelta(hours=3), False
    elif start_info.get("localDate"):
        day = datetime.fromisoformat(start_info["localDate"]).date()
        if start_info.get("localTime"):
            start = datetime.combine(day, time.fromisoformat(start_info["localTime"]), tzinfo=tz).astimezone(UTC)
            end, all_day = start + timedelta(hours=3), False
        else:
            start, all_day = date_to_utc(day), True
            end = start + timedelta(days=1)
    else:
        return None
    venue = (ev.get("_embedded", {}).get("venues") or [{}])[0]
    loc = venue.get("location") or {}
    address = ", ".join(x for x in (venue.get("address", {}).get("line1"), venue.get("postalCode"),
                                    venue.get("city", {}).get("name")) if x)
    hints = []
    for c in ev.get("classifications", []):
        hints += [c.get(k, {}).get("name", "") for k in ("segment", "genre")]
        if c.get("family"):
            hints.append("family")
    images = sorted(ev.get("images", []), key=lambda i: i.get("width", 0))
    return ActivityCandidate(
        title=ev.get("name", "(ohne Titel)"), start=start, end=end, all_day=all_day, external_id=ev.get("id"),
        description=ev.get("info") or ev.get("pleaseNote"), venue=venue.get("name"), address=address or None,
        location=GeoPoint(float(loc["latitude"]), float(loc["longitude"])) if loc.get("latitude") else None,
        url=ev.get("url"), image_url=images[len(images) // 2]["url"] if images else None, category_hints=hints,
    )
