"""Datenbank-Migrationen: Upgrade mit vorhandenen Daten, Reparatur, Atomarität."""
import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

import app.core.db as db
from app.core.db import _migration_engine, create_db_engine, run_migrations


def upgrade_to(path: Path, revision: str, script_dir: Path = db.MIGRATIONS_DIR) -> None:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(script_dir))
    engine = _migration_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)
    engine.dispose()


def db_with_events(path: Path) -> None:
    """Stand 0003 mit Familienmitglied, Kalender (Einzelzuordnung) und Termin."""
    upgrade_to(path, "0003")
    c = sqlite3.connect(path)
    c.execute("insert into familymember(name,color,sort_order) values('Lena','#000000',0)")
    c.execute("insert into account(provider,display_name) values('LOCAL','Lokal')")
    c.execute("insert into calendar(account_id,name,read_only,visible,is_default,default_member_id) "
              "values(1,'Familie',0,1,1,1)")
    c.execute("insert into event(calendar_id,title,start,end,all_day,timezone,exdates,created_at,updated_at,"
              "pending_push,deleted) values(1,'X','2026-11-24 10:00:00','2026-11-24 11:00:00',0,'Europe/Berlin',"
              "'[]','2026-11-20 10:00:00','2026-11-20 10:00:00',0,0)")
    c.commit()
    c.close()


def state(path: Path) -> dict:
    c = sqlite3.connect(path)
    out = {
        "version": c.execute("select version_num from alembic_version").fetchone()[0],
        "tables": {r[0] for r in c.execute("select name from sqlite_master where type='table'")},
        "calendar_columns": {r[1] for r in c.execute("pragma table_info(calendar)")},
        "events": c.execute("select count(*) from event").fetchone()[0],
        "fk_errors": c.execute("pragma foreign_key_check").fetchall(),
    }
    if "calendarmember" in out["tables"]:
        out["members"] = c.execute("select calendar_id, member_id from calendarmember").fetchall()
    c.close()
    return out


def test_upgrade_with_existing_events(tmp_path):
    """Neuaufbau der Kalender-Tabelle darf nicht an Verweisen der Termine scheitern."""
    path = tmp_path / "a.db"
    db_with_events(path)
    run_migrations(create_db_engine(path))
    s = state(path)
    assert s["version"] == "0004" and s["members"] == [(1, 1)] and s["events"] == 1
    assert "default_member_id" not in s["calendar_columns"] and s["fk_errors"] == []


def test_repairs_half_applied_0004(tmp_path):
    """Stand nach dem früheren Fehler: calendarmember angelegt, Version noch 0003."""
    path = tmp_path / "a.db"
    db_with_events(path)
    c = sqlite3.connect(path)
    c.execute("create table calendarmember (calendar_id integer not null, member_id integer not null, "
              "primary key (calendar_id, member_id))")
    c.execute("insert into calendarmember values (1, 1)")
    c.commit()
    c.close()
    run_migrations(create_db_engine(path))
    s = state(path)
    assert s["version"] == "0004" and s["members"] == [(1, 1)] and "default_member_id" not in s["calendar_columns"]


def test_failed_migration_leaves_database_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "a.db"
    db_with_events(path)
    scripts = tmp_path / "migrations"
    shutil.copytree(db.MIGRATIONS_DIR, scripts, ignore=shutil.ignore_patterns("__pycache__"))
    (scripts / "versions" / "0099_broken.py").write_text(
        'import sqlalchemy as sa\nfrom alembic import op\n'
        'revision = "0099"\ndown_revision = "0004"\nbranch_labels = None\ndepends_on = None\n\n'
        'def upgrade():\n'
        '    op.create_table("halbfertig", sa.Column("id", sa.Integer, primary_key=True))\n'
        '    raise RuntimeError("Absichtlicher Fehler")\n\n'
        'def downgrade():\n    pass\n', encoding="utf-8")
    monkeypatch.setattr(db, "MIGRATIONS_DIR", scripts)
    with pytest.raises(RuntimeError):
        run_migrations(create_db_engine(path))
    s = state(path)
    assert s["version"] == "0003"                              # nichts übernommen …
    assert "calendarmember" not in s["tables"] and "halbfertig" not in s["tables"]   # … auch nicht teilweise
    assert "default_member_id" in s["calendar_columns"] and s["events"] == 1


def test_foreign_keys_enforced_after_migration(tmp_path):
    """Die Anwendung selbst arbeitet weiterhin mit Fremdschlüssel-Prüfung."""
    path = tmp_path / "a.db"
    engine = create_db_engine(path)
    run_migrations(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
