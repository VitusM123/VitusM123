"""Adapter: Konfigurierbarer HTML-Scraper (CSS-Selektoren pro Website). Nutzungsbedingungen und robots.txt beachten."""
from app.providers.activities.base import ActivityCandidate, ActivityQuery, ActivitySource


class ScraperSource(ActivitySource):
    source_type = "scraper"

    def __init__(self, config: dict) -> None:
        self.config = config

    async def search(self, query: ActivityQuery) -> list[ActivityCandidate]:
        raise NotImplementedError
