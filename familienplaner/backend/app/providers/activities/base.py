"""Port: ActivitySource – Schnittstelle für Veranstaltungsquellen."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

import httpx


class SourceError(Exception):
    """Quelle nicht erreichbar oder Inhalt nicht lesbar."""


@dataclass
class GeoPoint:
    lat: float
    lon: float


@dataclass
class FetchWindow:
    """Was eine Quelle liefern soll."""
    date_from: date
    date_to: date
    center: GeoPoint | None = None      # nur für Quellen mit Umkreissuche (Ticketmaster)
    radius_km: float = 50
    timezone: str = "Europe/Berlin"


@dataclass
class ActivityCandidate:
    """Rohes, noch nicht dedupliziertes Ergebnis einer Quelle.

    ``start``/``end`` sind zeitzonenbewusst; bei ``all_day`` 00:00 UTC des Datums.
    """
    title: str
    start: datetime
    end: datetime | None = None
    all_day: bool = False
    external_id: str | None = None
    description: str | None = None
    venue: str | None = None
    address: str | None = None
    location: GeoPoint | None = None
    url: str | None = None
    image_url: str | None = None
    category_hints: list[str] = field(default_factory=list)


class ActivitySource(Protocol):
    source_type: str

    def __init__(self, config: dict) -> None: ...
    async def fetch(self, http: httpx.AsyncClient, window: FetchWindow) -> list[ActivityCandidate]: ...


async def get_text(http: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await http.get(url, follow_redirects=True,
                              headers={"User-Agent": "Familienplaner (selbst gehostet)"})
    except httpx.HTTPError as exc:
        raise SourceError(f"Quelle nicht erreichbar: {exc}") from exc
    if resp.status_code != 200:
        raise SourceError(f"Quelle antwortet mit HTTP {resp.status_code}")
    return resp.text
