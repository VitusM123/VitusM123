"""Adapter: Ticketmaster Discovery API (Geo-Suche über latlong + radius)."""
from app.providers.activities.base import ActivityCandidate, ActivityQuery, ActivitySource


class TicketmasterSource(ActivitySource):
    source_type = "api"

    def __init__(self, config: dict) -> None:
        self.config = config

    async def search(self, query: ActivityQuery) -> list[ActivityCandidate]:
        raise NotImplementedError
