"""Adapter: RSS-/Atom-Veranstaltungsfeeds."""
from app.providers.activities.base import ActivityCandidate, ActivityQuery, ActivitySource


class RssFeedSource(ActivitySource):
    source_type = "rss"

    def __init__(self, config: dict) -> None:
        self.config = config

    async def search(self, query: ActivityQuery) -> list[ActivityCandidate]:
        raise NotImplementedError
