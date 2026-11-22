"""Expansion wiederkehrender Termine (RFC 5545 RRULE) für ein Zeitfenster.

- Zeitgebundene Termine werden in ihrer eigenen Zeitzone expandiert, damit die Uhrzeit
  über die Sommer-/Winterzeitumstellung stabil bleibt.
- Ganztägige Termine werden als reine Datumsangaben expandiert.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

from app.core.timeutil import UTC
from app.services.errors import ValidationError

log = logging.getLogger(__name__)
MAX_OCCURRENCES = 2000  # Schutz vor sehr großen Fenstern mit FREQ=MINUTELY o. Ä.


def normalize_rrule(rule: str) -> str:
    rule = rule.strip()
    if rule.upper().startswith("RRULE:"):
        rule = rule[6:]
    return rule


def _align_until(rule: str, aware: bool) -> str:
    """dateutil verlangt, dass UNTIL und DTSTART beide mit oder beide ohne Zeitzone sind.

    Ganztägige Serien werden ohne Zeitzone expandiert → ``UNTIL=…Z`` bzw. ``UNTIL=YYYYMMDD`` wird
    zu lokalem Tagesende; zeitgebundene Serien erhalten ein UTC-``UNTIL``.
    """
    parts = []
    for part in rule.split(";"):
        key, _, value = part.partition("=")
        if key.upper() == "UNTIL" and value:
            day = value[:8]
            if aware and not value.endswith("Z"):
                value = f"{day}T235959Z" if len(value) == 8 else f"{value}Z"
            elif not aware:
                value = f"{day}T235959"
            part = f"UNTIL={value}"
        parts.append(part)
    return ";".join(parts)


def until_as_date(rule: str) -> str:
    """Bei ganztägigen Serien verlangt RFC 5545 ein UNTIL als Datum (``UNTIL=20270630``)."""
    parts = []
    for part in rule.split(";"):
        if part.upper().startswith("UNTIL=") and "T" in part:
            part = part.split("T")[0]
        parts.append(part)
    return ";".join(parts)


def validate_rrule(rule: str, dtstart: datetime) -> str:
    rule = normalize_rrule(rule)
    try:
        rrulestr(rule, dtstart=dtstart)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Ungültige Wiederholungsregel: {exc}") from exc
    return rule


def occurrence_key(start: datetime) -> str:
    return start.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def expand(
    *,
    start: datetime,
    end: datetime,
    rrule: str | None,
    all_day: bool,
    tz_name: str,
    window_start: datetime,
    window_end: datetime,
    display_tz: ZoneInfo,
    excluded: set[datetime] | None = None,
) -> list[tuple[datetime, datetime]]:
    """Liefert alle (Beginn, Ende)-Paare in UTC, die das Fenster [window_start, window_end) schneiden.

    ``display_tz`` ist die Zeitzone der Anzeige: Ganztägige Termine (00:00 UTC = Datum)
    werden gegen die lokale Wanduhrzeit des Fensters verglichen.
    ``excluded`` enthält ursprüngliche Beginnzeiten (UTC), die übersprungen werden
    (EXDATE sowie geänderte/abgesagte Einzelvorkommen).
    """
    duration = end - start
    excluded = {e.astimezone(UTC) for e in (excluded or set())}
    if all_day:
        window_start = window_start.astimezone(display_tz).replace(tzinfo=UTC)
        window_end = window_end.astimezone(display_tz).replace(tzinfo=UTC)

    if not rrule:
        return [(start, end)] if start < window_end and end > window_start else []

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = UTC

    if all_day:
        # Datumslogik ohne Zeitzone (00:00 naive)
        dtstart = start.astimezone(UTC).replace(tzinfo=None)
        lo = window_start.replace(tzinfo=None) - duration
        hi = window_end.replace(tzinfo=None)
        to_utc = lambda d: d.replace(tzinfo=UTC)  # noqa: E731
    else:
        dtstart = start.astimezone(tz)
        lo = window_start - duration
        hi = window_end
        to_utc = lambda d: d.astimezone(UTC)  # noqa: E731

    try:
        rule = rrulestr(_align_until(normalize_rrule(rrule), aware=not all_day), dtstart=dtstart)
    except (ValueError, TypeError):
        log.warning("Ungültige RRULE %r – Serie wird nur einmal angezeigt", rrule)
        return [(start, end)] if start < window_end and end > window_start else []

    result: list[tuple[datetime, datetime]] = []
    for occ in rule.xafter(lo, inc=False):
        if occ >= hi or len(result) >= MAX_OCCURRENCES:
            break
        occ_start = to_utc(occ)
        if occ_start in excluded:
            continue
        occ_end = to_utc(occ + duration) if all_day else occ_start + duration
        if occ_start < window_end and occ_end > window_start:
            result.append((occ_start, occ_end))
    return result
