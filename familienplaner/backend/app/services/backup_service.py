"""Tägliche Sicherung der SQLite-Datenbank (Online-Backup-API, konsistent auch bei laufendem Betrieb)."""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


def backup_database(db_path: Path, backup_dir: Path, keep: int) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"familienplaner-{datetime.now():%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(db_path) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    backups = sorted(backup_dir.glob("familienplaner-*.db"))
    for old in backups[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
    log.info("Datenbank gesichert: %s", target)
    return target
