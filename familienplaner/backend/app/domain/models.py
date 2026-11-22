"""Domänen-Entitäten (SQLModel). Siehe docs/ARCHITECTURE.md, Kap. 5.

Zeitkonvention:
- Alle Zeitpunkte sind zeitzonenbewusst und werden als UTC gespeichert (``UTCDateTime``).
- Ganztägige Termine: ``start``/``end`` = 00:00 UTC des Datums, ``end`` exklusiv.
- ``Event.timezone`` ist die Zeitzone, in der wiederkehrende Termine expandiert werden
  (damit 08:00 auch nach der Zeitumstellung 08:00 bleibt).
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, LargeBinary
from sqlmodel import JSON, Field, SQLModel

from app.core.timeutil import utcnow
from app.core.types import UTCDateTime


def _ts(nullable: bool = False, index: bool = False) -> Column:
    return Column(UTCDateTime(), nullable=nullable, index=index)


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
    avatar: str | None = None          # Emoji oder Bild-URL
    sort_order: int = 0


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    provider: ProviderType
    display_name: str
    credentials_encrypted: bytes | None = Field(default=None, sa_column=Column(LargeBinary, nullable=True))
    last_sync: datetime | None = Field(default=None, sa_column=_ts(nullable=True))
    last_error: str | None = None


class Calendar(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    remote_id: str | None = None
    name: str
    color: str | None = None
    read_only: bool = False
    visible: bool = True
    is_default: bool = False           # Ziel für neue Termine
    default_member_id: int | None = Field(default=None, foreign_key="familymember.id")
    sync_token: str | None = None


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    calendar_id: int = Field(foreign_key="calendar.id", index=True)
    remote_id: str | None = Field(default=None, index=True)
    etag: str | None = None
    title: str
    description: str | None = None
    location: str | None = None
    start: datetime = Field(sa_column=_ts(index=True))
    end: datetime = Field(sa_column=_ts(index=True))
    all_day: bool = False
    timezone: str = "Europe/Berlin"
    # Wiederholung: RRULE ohne Präfix, z. B. "FREQ=WEEKLY;BYDAY=MO,WE"
    rrule: str | None = None
    # Ausgenommene Vorkommen (ISO-UTC-Zeitstempel des ursprünglichen Beginns)
    exdates: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # Geändertes/abgesagtes Einzelvorkommen einer Serie
    recurrence_master_id: int | None = Field(default=None, foreign_key="event.id", index=True)
    original_start: datetime | None = Field(default=None, sa_column=_ts(nullable=True))
    category: str | None = None
    activity_id: int | None = Field(default=None, foreign_key="activity.id")
    created_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
    pending_push: bool = Field(default=False, index=True)   # Outbox-Flag
    deleted: bool = False


class EventMember(SQLModel, table=True):
    event_id: int = Field(foreign_key="event.id", primary_key=True)
    member_id: int = Field(foreign_key="familymember.id", primary_key=True)


class ActivitySource(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    type: ActivitySourceType
    name: str
    config: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    enabled: bool = True


class Activity(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="activitysource.id", index=True)
    external_id: str | None = None
    title: str
    description: str | None = None
    category: ActivityCategory = ActivityCategory.OTHER
    start: datetime = Field(sa_column=_ts(index=True))
    end: datetime | None = Field(default=None, sa_column=_ts(nullable=True))
    venue: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    url: str | None = None
    image_url: str | None = None
    fingerprint: str = Field(index=True)
    fetched_at: datetime = Field(default_factory=utcnow, sa_column=_ts())


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class GeocodeCache(SQLModel, table=True):
    query: str = Field(primary_key=True)
    lat: float
    lon: float
    cached_at: datetime = Field(default_factory=utcnow, sa_column=_ts())
