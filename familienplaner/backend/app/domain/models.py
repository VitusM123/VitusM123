"""Domänen-Entitäten (SQLModel). Siehe docs/ARCHITECTURE.md, Kap. 5."""
from datetime import datetime
from enum import Enum

from sqlmodel import JSON, Column, Field, SQLModel


class ProviderType(str, Enum):
    GOOGLE = "google"
    ICLOUD = "icloud"
    LOCAL = "local"


class ActivityCategory(str, Enum):
    OPEN_DAY = "open_day"          # Tag der offenen Tür
    FAIR = "fair"                  # Messe
    EXHIBITION = "exhibition"      # Ausstellung
    MARKET = "market"              # Markt / Flohmarkt
    FESTIVAL = "festival"
    CONCERT = "concert"
    THEATER = "theater"
    SPORTS = "sports"
    KIDS = "kids"
    WORKSHOP = "workshop"
    OTHER = "other"


class ActivitySourceType(str, Enum):
    ICAL = "ical"
    RSS = "rss"
    API = "api"
    SCRAPER = "scraper"


class FamilyMember(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    color: str
    avatar: str | None = None
    sort_order: int = 0


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    provider: ProviderType
    display_name: str
    credentials_encrypted: bytes | None = None
    last_sync: datetime | None = None


class Calendar(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    remote_id: str | None = None
    name: str
    color: str | None = None
    read_only: bool = False
    visible: bool = True
    default_member_id: int | None = Field(default=None, foreign_key="familymember.id")
    sync_token: str | None = None


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    calendar_id: int = Field(foreign_key="calendar.id")
    remote_id: str | None = None
    etag: str | None = None
    title: str
    description: str | None = None
    location: str | None = None
    start: datetime
    end: datetime
    all_day: bool = False
    rrule: str | None = None
    timezone: str = "Europe/Berlin"
    category: str | None = None
    activity_id: int | None = Field(default=None, foreign_key="activity.id")
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    pending_push: bool = False     # Outbox-Flag für Offline-Änderungen
    deleted: bool = False


class EventMember(SQLModel, table=True):
    event_id: int = Field(foreign_key="event.id", primary_key=True)
    member_id: int = Field(foreign_key="familymember.id", primary_key=True)


class ActivitySource(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    type: ActivitySourceType
    name: str
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    enabled: bool = True


class Activity(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="activitysource.id")
    external_id: str | None = None
    title: str
    description: str | None = None
    category: ActivityCategory = ActivityCategory.OTHER
    start: datetime
    end: datetime | None = None
    venue: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    url: str | None = None
    image_url: str | None = None
    fingerprint: str = Field(index=True)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: dict = Field(default_factory=dict, sa_column=Column(JSON))


class GeocodeCache(SQLModel, table=True):
    query: str = Field(primary_key=True)
    lat: float
    lon: float
    cached_at: datetime = Field(default_factory=datetime.utcnow)
