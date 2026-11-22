"""Geocoding (Nominatim, max. 1 Anfrage/s, gecacht) und Umkreisberechnung."""
from app.providers.activities.base import GeoPoint


class GeoService:
    async def geocode(self, address: str) -> GeoPoint | None:
        raise NotImplementedError

    @staticmethod
    def distance_km(a: GeoPoint, b: GeoPoint) -> float:
        """Haversine-Distanz."""
        raise NotImplementedError
