"""SQLAlchemy-Typen."""
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Speichert Zeitpunkte als naive UTC-Werte (SQLite kennt keine Zeitzonen)
    und liefert sie als zeitzonenbewusste UTC-Datetimes zurück.

    Naive Werte werden abgelehnt, damit Zeitzonenfehler sofort auffallen.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime – bitte zeitzonenbewusste Werte verwenden")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
