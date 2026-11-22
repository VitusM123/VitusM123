"""Geocoding über OpenStreetMap/Nominatim und Umkreisberechnung.

Nominatim-Nutzungsregeln: höchstens 1 Anfrage pro Sekunde, eindeutiger User-Agent, Ergebnisse
zwischenspeichern. Ergebnisse landen dauerhaft in der Tabelle ``geocodecache``. Nicht gefundene
Adressen werden für die Laufzeit gemerkt und nicht erneut angefragt.
"""
import asyncio
import logging
import math
import time

import httpx
from sqlmodel import Session

from app import __version__
from app.domain.models import GeocodeCache
from app.providers.activities.base import GeoPoint

log = logging.getLogger(__name__)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def distance_km(a: GeoPoint, b: GeoPoint) -> float:
    """Haversine-Distanz in km."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def normalize_query(text: str) -> str:
    return " ".join(text.lower().replace("\n", " ").split())[:250]


class GeoService:
    def __init__(self, countrycodes: str = "de,at,ch", url: str = NOMINATIM_URL, min_interval: float = 1.1) -> None:
        self.countrycodes = countrycodes
        self.url = url
        self.min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._misses: set[str] = set()

    async def geocode(self, session: Session, http: httpx.AsyncClient, query: str) -> GeoPoint | None:
        key = normalize_query(query)
        if len(key) < 3 or key in self._misses:
            return None
        cached = session.get(GeocodeCache, key)
        if cached:
            return GeoPoint(cached.lat, cached.lon)
        async with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                resp = await http.get(self.url, params={
                    "q": query, "format": "jsonv2", "limit": 1, "countrycodes": self.countrycodes,
                }, headers={"User-Agent": f"Familienplaner/{__version__} (selbst gehostet)",
                            "Accept-Language": "de"})
            finally:
                self._last = time.monotonic()
        if resp.status_code != 200:
            log.warning("Geocoding fehlgeschlagen (HTTP %s) für %r", resp.status_code, query)
            return None
        data = resp.json()
        if not data:
            self._misses.add(key)
            return None
        point = GeoPoint(float(data[0]["lat"]), float(data[0]["lon"]))
        session.add(GeocodeCache(query=key, lat=point.lat, lon=point.lon))
        session.commit()
        return point
