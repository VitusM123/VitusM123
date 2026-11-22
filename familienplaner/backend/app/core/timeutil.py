"""Hilfsfunktionen für Zeitzonen und Datumsangaben."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_aware(value: datetime, tz: ZoneInfo) -> datetime:
    """Naive Werte werden als Ortszeit in ``tz`` interpretiert."""
    return value.replace(tzinfo=tz) if value.tzinfo is None else value


def date_to_utc(d: date) -> datetime:
    """Ganztägige Termine: Datum wird als 00:00 UTC gespeichert (reine Datumssemantik)."""
    return datetime.combine(d, time.min, tzinfo=UTC)


def utc_to_date(value: datetime) -> date:
    return value.astimezone(UTC).date()


def local_day_bounds(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[Beginn, Ende) eines lokalen Kalendertages als UTC-Zeitpunkte."""
    start = datetime.combine(d, time.min, tzinfo=tz)
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def in_time_range(now: time, start: time, end: time) -> bool:
    """Liegt ``now`` in [start, end)? Bereiche über Mitternacht werden unterstützt."""
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end
