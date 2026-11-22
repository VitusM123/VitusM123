"""Hintergrundjobs (APScheduler).

Geplante Jobs:
- calendar_sync        alle `sync.interval_minutes`
- activity_refresh     alle `activities.refresh_hours`
- eink_refresh         alle `display.eink.refresh_minutes` (nur im E-Ink-Modus)
- night_mode           Display aus/an zu festen Zeiten
- db_backup            täglich
"""


def start_scheduler() -> None:
    raise NotImplementedError


def stop_scheduler() -> None:
    raise NotImplementedError
