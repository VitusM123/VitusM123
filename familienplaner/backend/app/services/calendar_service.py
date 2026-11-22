"""Lese- und Schreibzugriffe für die Kalenderansichten.

Wiederkehrende Termine (RRULE) werden beim Lesen für das angefragte Zeitfenster expandiert.
"""
from datetime import datetime


class CalendarService:
    def list_events(self, start: datetime, end: datetime,
                    member_ids: list[int] | None = None) -> list:
        raise NotImplementedError

    def family_table(self, start: datetime, end: datetime) -> dict:
        """Termine gruppiert nach Tag × Familienmitglied (für FamilyTableView)."""
        raise NotImplementedError

    def create_event(self, draft, calendar_id: int, member_ids: list[int]):
        raise NotImplementedError

    def update_event(self, event_id: int, changes: dict):
        raise NotImplementedError

    def delete_event(self, event_id: int) -> None:
        raise NotImplementedError
