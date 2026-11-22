"""Freizeitaktivitäten: Suche über alle Quellen, Normalisierung, Geo-Filter,
Deduplizierung, Kategorisierung und Übernahme in den Kalender."""
from app.providers.activities.base import ActivityQuery


class ActivityService:
    async def search(self, query: ActivityQuery) -> list:
        raise NotImplementedError

    async def refresh_cache(self) -> None:
        """Periodischer Abruf für die Standardsuche (Heimatort + Standard-Umkreis)."""
        raise NotImplementedError

    def add_to_calendar(self, activity_id: int, calendar_id: int, member_ids: list[int]):
        raise NotImplementedError

    @staticmethod
    def fingerprint(title: str, start, venue: str | None) -> str:
        raise NotImplementedError
