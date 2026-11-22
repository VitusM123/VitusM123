"""Alembic-Umgebung. Wird programmatisch aus app.core.db.run_migrations aufgerufen
oder per CLI: ``alembic -x db=data/familienplaner.db upgrade head``."""
from alembic import context
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import app.domain.models  # noqa: F401  (registriert die Tabellen)

target_metadata = SQLModel.metadata


def run() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _configure_and_run(connection)
        return
    db = context.get_x_argument(as_dictionary=True).get("db", "data/familienplaner.db")
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        _configure_and_run(conn)


def _configure_and_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True,
                      transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()


run()
