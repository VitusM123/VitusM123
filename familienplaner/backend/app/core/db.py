"""Datenbank: Engine (SQLite, WAL), Migrationen (Alembic), Session-Dependency, Startdaten."""
import logging
from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import Request
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from app.config import Settings
from app.domain.models import Account, Calendar, ProviderType

log = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def create_db_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @sa_event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")      # robuster bei Stromausfall, parallele Leser
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")    # schont die SD-Karte
        cur.close()

    return engine


def _migration_engine(url) -> Engine:
    """Eigene Engine für Migrationen:

    - Fremdschlüssel-Prüfung aus: SQLite kann Spalten nur durch Neuaufbau der Tabelle ändern;
      dabei würden Verweise (z. B. Termine → Kalender) sonst den Umbau abbrechen.
    - Echte Transaktion (``BEGIN`` selbst senden): pysqlite führt DDL sonst ohne Transaktion aus,
      und eine fehlgeschlagene Migration hinterließe eine halb umgebaute Datenbank.
    """
    engine = create_engine(url, connect_args={"check_same_thread": False, "isolation_level": None})

    @sa_event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")

    @sa_event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    return engine


def run_migrations(engine: Engine) -> None:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    migration_engine = _migration_engine(engine.url)
    try:
        with migration_engine.begin() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
            problems = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if problems:
                log.warning("Datenbank enthält %d ungültige Verweise: %s", len(problems), problems[:5])
    finally:
        migration_engine.dispose()


def seed_defaults(engine: Engine) -> None:
    """Legt beim ersten Start ein lokales Konto mit dem Kalender „Familie“ an."""
    with Session(engine) as session:
        local = session.exec(select(Account).where(Account.provider == ProviderType.LOCAL)).first()
        if local is None:
            local = Account(provider=ProviderType.LOCAL, display_name="Lokal")
            session.add(local)
            session.flush()
            session.add(Calendar(account_id=local.id, name="Familie", color="#3E7CB1", is_default=True))
            session.commit()
            log.info("Lokales Konto und Kalender „Familie“ angelegt")


def init_db(settings: Settings) -> Engine:
    engine = create_db_engine(settings.database.path)
    run_migrations(engine)
    seed_defaults(engine)
    return engine


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI-Dependency."""
    with Session(request.app.state.engine) as session:
        yield session
