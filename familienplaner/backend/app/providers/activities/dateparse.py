"""Erkennung deutscher Datums- und Zeitangaben in Freitext (RSS, Webseiten).

Beispiele: „24.11.2026, 18:30 Uhr“, „Sa, 28.11. 10–16 Uhr“, „28. November 2026“, „2026-11-28T10:00“.
"""
import re
from datetime import date, datetime, time

MONTHS = {
    "jan": 1, "januar": 1, "feb": 2, "februar": 2, "mär": 3, "märz": 3, "maerz": 3, "mrz": 3, "apr": 4, "april": 4,
    "mai": 5, "jun": 6, "juni": 6, "jul": 7, "juli": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10, "nov": 11, "november": 11, "dez": 12, "dezember": 12,
}
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?")
# Jahr: vierstellig (auch nach Leerzeichen) oder zweistellig direkt nach dem Punkt („28.11.26“);
# „28.11. 10–16 Uhr“ darf die 10 nicht als Jahr lesen
_NUMERIC = re.compile(r"(?<!\d)(\d{1,2})\.\s?(\d{1,2})\.(?:\s?(\d{4})(?!\d)|(\d{2})(?![\d.:]))?")
_WORDS = re.compile(r"(?<!\d)(\d{1,2})\.\s*(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s*(\d{4})?",
                    re.IGNORECASE)
# „18:30“, „18.30 Uhr“, „19 Uhr“, „10–16 Uhr“ (Beginn der Spanne)
_TIME = re.compile(r"(?<![\d.])(\d{1,2})[:.](\d{2})(?!\d)"
                   r"|(?<![\d.])(\d{1,2})(?:\s*[–-]\s*\d{1,2}(?:[:.]\d{2})?)?\s*uhr", re.IGNORECASE)


def _year(raw: str | None, month: int, day: int, today: date) -> int:
    if raw:
        y = int(raw)
        return y + 2000 if y < 100 else y
    # ohne Jahr: nächstes Vorkommen ab heute (Termine im Januar, die im Dezember angekündigt werden)
    candidate = today.year
    try:
        if date(candidate, month, day) < today.replace(day=1):
            candidate += 1
    except ValueError:
        pass
    return candidate


def parse_datetime(text: str, today: date | None = None) -> tuple[datetime, bool] | None:
    """Erstes Datum (+ Uhrzeit) im Text. Rückgabe: (naive Ortszeit, hat_uhrzeit) oder None."""
    if not text:
        return None
    today = today or date.today()
    found: tuple[int, int, int, int] | None = None   # (Position, Jahr, Monat, Tag)
    for regex, kind in ((_ISO, "iso"), (_NUMERIC, "num"), (_WORDS, "word")):
        m = regex.search(text)
        if not m:
            continue
        try:
            if kind == "iso":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if m.group(4):
                    return datetime(y, mo, d, int(m.group(4)), int(m.group(5))), True
            elif kind == "num":
                d, mo = int(m.group(1)), int(m.group(2))
                y = _year(m.group(3) or m.group(4), mo, d, today)
            else:
                d, mo = int(m.group(1)), MONTHS[m.group(2).lower().rstrip(".")]
                y = _year(m.group(3), mo, d, today)
            date(y, mo, d)
        except (ValueError, KeyError):
            continue
        if found is None or m.start() < found[0]:
            found = (m.end(), y, mo, d)
    if found is None:
        return None
    end_pos, y, mo, d = found
    t = _TIME.search(text, end_pos)      # Uhrzeit steht hinter dem Datum
    if t:
        hour = int(t.group(1) or t.group(3))
        minute = int(t.group(2) or 0)
        if 0 <= hour < 24 and 0 <= minute < 60:
            return datetime.combine(date(y, mo, d), time(hour, minute)), True
    return datetime(y, mo, d), False
