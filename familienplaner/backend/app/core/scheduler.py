"""Hintergrundjobs (APScheduler, läuft im Event-Loop des Backends).

- calendar_sync   alle ``sync.interval_minutes``
- minute_tick     jede Minute: Nachtmodus, automatischer Theme-Wechsel
- db_backup       täglich 03:17
(activity_refresh und eink_refresh folgen mit den jeweiligen Ausbaustufen)
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from sqlmodel import Session

from app.services.backup_service import backup_database
from app.services.settings_service import SettingsService

log = logging.getLogger(__name__)


async def minute_tick(app: FastAPI) -> None:
    state = app.state
    tz = ZoneInfo(state.settings.locale.timezone)
    now = datetime.now(tz)
    with Session(state.engine) as session:
        user = SettingsService(session, state.settings).get()
    if state.display.tick(now, user.night_mode):
        await state.bus.publish("display.changed", state.display.state().model_dump())
    theme_id = state.themes.resolve_active_id(user, now)
    if theme_id != getattr(state, "active_theme_id", None):
        previous = getattr(state, "active_theme_id", None)
        state.active_theme_id = theme_id
        if previous is not None:
            await state.bus.publish("theme.changed", {"theme": theme_id})


async def run_backup(app: FastAPI) -> None:
    db = app.state.settings.database
    try:
        backup_database(db.path, db.backup_dir, db.backup_keep)
    except Exception:
        log.exception("Datenbank-Backup fehlgeschlagen")


def create_scheduler(app: FastAPI) -> AsyncIOScheduler:
    settings = app.state.settings
    scheduler = AsyncIOScheduler(timezone=settings.locale.timezone)
    scheduler.add_job(app.state.sync.sync_all, "interval", minutes=settings.sync.interval_minutes,
                      id="calendar_sync", max_instances=1, coalesce=True)
    scheduler.add_job(minute_tick, "cron", second=5, args=[app], id="minute_tick",
                      max_instances=1, coalesce=True)
    scheduler.add_job(run_backup, "cron", hour=3, minute=17, args=[app], id="db_backup")
    return scheduler
