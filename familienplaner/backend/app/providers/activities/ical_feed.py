"""Adapter: Generische iCal/ICS-Feeds (Museen, Städte, Schulen, Messegelände)."""
from app.providers.activities.base import ActivityCandidate, ActivityQuery, ActivitySource


class ICalFeedSource(ActivitySource):
    source_type = "ical"

    def __init__(self, config: dict) -> None:
        self.config = config

    async def search(self, query: ActivityQuery) -> list[ActivityCandidate]:
        raise NotImplementedError
