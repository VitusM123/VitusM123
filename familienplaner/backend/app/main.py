"""App-Factory: verdrahtet Router, Lifespan (DB, Scheduler) und statisches Frontend."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import accounts, activities, calendar, display, members, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: DB initialisieren, Scheduler starten, Event-Bus anbinden
    yield
    # TODO: Scheduler stoppen


def create_app() -> FastAPI:
    app = FastAPI(title="Familienplaner", version="0.1.0", lifespan=lifespan)
    for module in (calendar, members, accounts, activities, settings, display):
        app.include_router(module.router)
    # TODO: frontend/dist als StaticFiles unter "/" mounten
    return app


app = create_app()
