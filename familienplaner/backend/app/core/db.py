"""Datenbank-Engine (SQLite) und Session-Handling."""


def init_db() -> None:
    """TODO: Engine erzeugen, WAL-Modus aktivieren, Migrationen (Alembic) ausführen."""
    raise NotImplementedError


def get_session():
    """TODO: FastAPI-Dependency, liefert eine SQLModel-Session."""
    raise NotImplementedError
