"""Port: CalendarProvider – Schnittstelle für externe Kalender."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.domain.models import Account, Calendar, Event


@dataclass
class RemoteCalendar:
    remote_id: str
    name: str
    color: str | None
    read_only: bool


@dataclass
class RemoteEvent:
    remote_id: str
    etag: str | None
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    description: str | None = None
    location: str | None = None
    rrule: str | None = None
    updated: datetime | None = None


@dataclass
class EventDraft:
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    description: str | None = None
    location: str | None = None
    rrule: str | None = None


@dataclass
class ChangeSet:
    upserted: list[RemoteEvent] = field(default_factory=list)
    deleted_remote_ids: list[str] = field(default_factory=list)
    next_sync_token: str | None = None
    full_resync_required: bool = False


class CalendarProvider(Protocol):
    provider_id: str

    async def authenticate(self, account: Account) -> None: ...
    async def list_calendars(self) -> list[RemoteCalendar]: ...
    async def fetch_changes(self, calendar: Calendar, sync_token: str | None) -> ChangeSet: ...
    async def create_event(self, calendar: Calendar, event: EventDraft) -> RemoteEvent: ...
    async def update_event(self, calendar: Calendar, event: Event) -> RemoteEvent: ...
    async def delete_event(self, calendar: Calendar, event: Event) -> None: ...
