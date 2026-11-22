from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.recurrence import expand

BERLIN = ZoneInfo("Europe/Berlin")
UTC = timezone.utc


def _local(*args):
    return datetime(*args, tzinfo=BERLIN)


def test_weekly_keeps_local_time_across_dst():
    start = _local(2026, 10, 19, 8, 0)  # Montag, Sommerzeit
    spans = expand(
        start=start.astimezone(UTC), end=(start + timedelta(hours=1)).astimezone(UTC),
        rrule="FREQ=WEEKLY", all_day=False, tz_name="Europe/Berlin",
        window_start=_local(2026, 10, 19), window_end=_local(2026, 11, 3), display_tz=BERLIN,
    )
    local_hours = [s.astimezone(BERLIN).hour for s, _ in spans]
    assert len(spans) == 3
    assert local_hours == [8, 8, 8]          # auch nach der Umstellung am 25.10.
    assert spans[0][0].hour == 6 and spans[2][0].hour == 7   # in UTC verschoben


def test_exdates_and_count():
    start = datetime(2026, 11, 2, 15, tzinfo=UTC)
    spans = expand(
        start=start, end=start + timedelta(hours=1), rrule="RRULE:FREQ=DAILY;COUNT=5", all_day=False,
        tz_name="UTC", window_start=start, window_end=start + timedelta(days=30), display_tz=UTC,
        excluded={start + timedelta(days=1)},
    )
    assert len(spans) == 4


def test_all_day_uses_date_semantics():
    # Ganztägig am 22.11. (00:00 UTC als Datum). Fenster = lokaler 22.11. in Berlin
    start = datetime(2026, 11, 22, tzinfo=UTC)
    win_start, win_end = _local(2026, 11, 22), _local(2026, 11, 23)
    spans = expand(start=start, end=start + timedelta(days=1), rrule=None, all_day=True, tz_name="Europe/Berlin",
                   window_start=win_start, window_end=win_end, display_tz=BERLIN)
    assert len(spans) == 1
    # Der Vortag darf nicht hineinrutschen (Fenster beginnt 23:00 UTC am 21.11.)
    prev = datetime(2026, 11, 21, tzinfo=UTC)
    assert expand(start=prev, end=prev + timedelta(days=1), rrule=None, all_day=True, tz_name="Europe/Berlin",
                  window_start=win_start, window_end=win_end, display_tz=BERLIN) == []


def test_all_day_series_with_until():
    # Frontend erzeugt UNTIL als UTC-Zeitpunkt, Google liefert bei Ganztägigem ein Datum
    start = datetime(2026, 11, 23, tzinfo=UTC)
    for rule in ("FREQ=WEEKLY;BYDAY=MO;UNTIL=20261214T235959Z", "FREQ=WEEKLY;BYDAY=MO;UNTIL=20261214"):
        spans = expand(start=start, end=start + timedelta(days=1), rrule=rule, all_day=True, tz_name="Europe/Berlin",
                       window_start=start, window_end=start + timedelta(days=60), display_tz=BERLIN)
        assert [s.date().isoformat() for s, _ in spans] == ["2026-11-23", "2026-11-30", "2026-12-07", "2026-12-14"]


def test_timed_series_with_date_only_until():
    start = datetime(2026, 11, 23, 15, tzinfo=UTC)
    spans = expand(start=start, end=start + timedelta(hours=1), rrule="FREQ=DAILY;UNTIL=20261125", all_day=False,
                   tz_name="Europe/Berlin", window_start=start, window_end=start + timedelta(days=10),
                   display_tz=BERLIN)
    assert len(spans) == 3


def test_invalid_rrule_falls_back_to_single():
    start = datetime(2026, 11, 22, 10, tzinfo=UTC)
    spans = expand(start=start, end=start + timedelta(hours=1), rrule="FREQ=NONSENSE", all_day=False,
                   tz_name="UTC", window_start=start - timedelta(days=1), window_end=start + timedelta(days=1),
                   display_tz=UTC)
    assert spans == [(start, start + timedelta(hours=1))]
