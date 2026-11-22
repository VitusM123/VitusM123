"""Registry: Quell-Typ → Adapter-Klasse."""
from app.providers.activities.ical_feed import ICalFeedSource
from app.providers.activities.rss_feed import RssFeedSource
from app.providers.activities.scraper import ScraperSource
from app.providers.activities.ticketmaster import TicketmasterSource

SOURCES = {
    "ical": ICalFeedSource,
    "rss": RssFeedSource,
    "ticketmaster": TicketmasterSource,
    "scraper": ScraperSource,
}
SECRET_FIELDS = {"ticketmaster": ["api_key"]}
