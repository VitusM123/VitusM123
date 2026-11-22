"""Port: ActivitySource – Schnittstelle für Veranstaltungsquellen."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from app.domain.models import ActivityCategory


@dataclass
class GeoPoint:
    lat: float
    lon: float


@dataclass
class ActivityQuery:
    center: GeoPoint
    radius_km: float
    date_from: date
    date_to: date
    categories: list[ActivityCategory] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class ActivityCandidate:
    """Rohes, noch nicht dedupliziertes Ergebnis einer Quelle."""
    external_id: str | None
    title: str
    start: datetime
    end: datetime | None = None
    description: str | None = None
    venue: str | None = None
    address: str | None = None
    location: GeoPoint | None = None
    url: str | None = None
    image_url: str | None = None
    category_hint: str | None = None


class ActivitySource(Protocol):
    source_type: str

    def __init__(self, config: dict) -> None: ...
    async def search(self, query: ActivityQuery) -> list[ActivityCandidate]: ...
