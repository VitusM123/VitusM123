"""Registry: Quell-Typ -> ActivitySource-Klasse."""
from app.providers.activities.base import ActivitySource
from app.providers.activities.ical_feed import ICalFeedSource
from app.providers.activities.rss_feed import RssFeedSource
from app.providers.activities.scraper import ScraperSource
from app.providers.activities.ticketmaster import TicketmasterSource

SOURCES: dict[str, type[ActivitySource]] = {
    "ical": ICalFeedSource,
    "rss": RssFeedSource,
    "ticketmaster": TicketmasterSource,
    "scraper": ScraperSource,
}
