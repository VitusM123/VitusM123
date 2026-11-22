"""App-Factory: verdrahtet Konfiguration, Datenbank, Services, Router, Scheduler und Frontend."""
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import accounts, activities, auth, calendar, display, members, settings, system
from app.config import Settings, load_settings
from app.core.db import init_db
from app.core.events import EventBus
from app.core.scheduler import create_scheduler
from app.core.security import LoginThrottle, SecretBox
from app.services.display_service import DisplayService
from app.services.errors import DomainError
from app.services.google_service import PendingAuth, make_provider_factory
from app.services.sync_service import SyncService
from app.services.theme_service import ThemeService

log = logging.getLogger("familienplaner")


def create_app(
    config: Settings | None = None,
    *,
    start_scheduler: bool = True,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """``http_transport`` ersetzt in Tests den Netzwerkzugriff (z. B. ``httpx.MockTransport``)."""
    cfg = config or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if start_scheduler:
            scheduler = create_scheduler(app)
            scheduler.start()
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="Familienplaner", version=__version__, lifespan=lifespan)

    # Zustand, der während der Laufzeit geteilt wird
    app.state.settings = cfg
    app.state.engine = init_db(cfg)
    app.state.secrets = SecretBox(cfg.security.secret_key_file)
    app.state.bus = EventBus()
    app.state.themes = ThemeService(cfg.custom_themes_dir)
    app.state.display = DisplayService(cfg.display.backlight_path)
    app.state.sync = SyncService(
        app.state.engine, app.state.bus, cfg, app.state.secrets,
        provider_factory=make_provider_factory(cfg, app.state.secrets), http_transport=http_transport,
    )
    app.state.google_pending = PendingAuth()
    app.state.login_throttle = LoginThrottle()

    @app.exception_handler(DomainError)
    async def _domain_error(_request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    for module in (system, auth, calendar, members, accounts, activities, settings, display):
        app.include_router(module.router)

    dist = cfg.resolve_frontend_dist()
    if dist:
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        log.info("Kein Frontend-Build gefunden – nur API verfügbar (/docs)")
    return app


def app_factory() -> FastAPI:
    """Einstiegspunkt für uvicorn: ``uvicorn --factory app.main:app_factory``."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    return create_app()
