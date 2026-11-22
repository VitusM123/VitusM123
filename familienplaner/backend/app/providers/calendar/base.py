"""Port: CalendarProvider – Schnittstelle für externe Kalender (Google, iCloud).

Zeitkonvention wie im Domänenmodell: zeitzonenbewusste UTC-Zeitpunkte, ganztägige Termine
als 00:00 UTC des Datums (Ende exklusiv).
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class ProviderError(Exception):
    """Allgemeiner Fehler beim externen Kalenderdienst."""


class AuthError(ProviderError):
    """Zugangsdaten ungültig/abgelaufen – das Konto muss neu verbunden werden."""


class SyncTokenExpired(ProviderError):
    """Delta-Token ungültig – vollständige Neusynchronisation nötig."""


class RemoteNotFound(ProviderError):
    """Objekt existiert remote nicht (mehr)."""


@dataclass
class RemoteCalendar:
    remote_id: str
    name: str
    color: str | None = None
    read_only: bool = False
    primary: bool = False
    selected: bool = True
    timezone: str | None = None


@dataclass
class RemoteEvent:
    """Ein Termin, wie ihn der Provider liefert (normalisiert)."""

    remote_id: str
    etag: str | None = None
    cancelled: bool = False
    title: str = ""
    description: str | None = None
    location: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    timezone: str | None = None
    rrule: str | None = None
    exdates: list[datetime] = field(default_factory=list)
    # Einzelvorkommen einer Serie
    recurring_remote_id: str | None = None
    original_start: datetime | None = None
    # Zuordnung zu Familienmitgliedern (vom Familienplaner selbst gespeichert); None = unbekannt
    member_ids: list[int] | None = None
    updated: datetime | None = None


@dataclass
class OutgoingEvent:
    """Lokaler Termin, aufbereitet zum Hochladen."""

    title: str
    start: datetime
    end: datetime
    all_day: bool
    timezone: str
    description: str | None = None
    location: str | None = None
    rrule: str | None = None
    exdates: list[datetime] = field(default_factory=list)
    member_ids: list[int] = field(default_factory=list)
    recurring_remote_id: str | None = None
    original_start: datetime | None = None


@dataclass
class ChangeSet:
    events: list[RemoteEvent] = field(default_factory=list)
    next_sync_token: str | None = None
    full: bool = False          # True = vollständige Liste (nicht enthaltene Termine wurden gelöscht)


class CalendarProvider(Protocol):
    provider_id: str

    async def list_calendars(self) -> list[RemoteCalendar]: ...
    async def fetch_changes(self, calendar_remote_id: str, sync_token: str | None) -> ChangeSet: ...
    async def create_event(self, calendar_remote_id: str, event: OutgoingEvent) -> tuple[str, str | None]: ...
    async def update_event(self, calendar_remote_id: str, remote_id: str, event: OutgoingEvent) -> str | None: ...
    async def delete_event(self, calendar_remote_id: str, remote_id: str) -> None: ...
    def instance_id(self, master_remote_id: str, original_start: datetime, all_day: bool) -> str: ...
