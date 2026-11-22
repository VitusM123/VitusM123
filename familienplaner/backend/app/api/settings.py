"""Einstellungen und Themes."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from app.core.deps import get_settings_service, get_theme_service, require_admin
from app.schemas import Theme, ThemeSelect, UserSettings, UserSettingsUpdate
from app.services.errors import ValidationError
from app.services.settings_service import SettingsService
from app.services.theme_service import ThemeService

router = APIRouter(prefix="/api", tags=["settings"])


def _now(request: Request) -> datetime:
    return datetime.now(ZoneInfo(request.app.state.settings.locale.timezone))


def _validate_theme_ids(themes: ThemeService, changes: UserSettingsUpdate) -> None:
    for field in ("theme", "day_theme", "night_theme"):
        value = getattr(changes, field)
        if value is not None and not themes.exists(value):
            raise ValidationError(f"Theme „{value}“ existiert nicht")


async def _publish_theme_if_changed(request: Request, themes: ThemeService, user: UserSettings) -> None:
    active = themes.resolve_active_id(user, _now(request))
    if active != getattr(request.app.state, "active_theme_id", None):
        request.app.state.active_theme_id = active
        await request.app.state.bus.publish("theme.changed", {"theme": active})


@router.get("/themes", response_model=list[Theme])
def list_themes(themes: ThemeService = Depends(get_theme_service)):
    return themes.list_themes()


@router.get("/themes/active", response_model=Theme)
def active_theme(request: Request, themes: ThemeService = Depends(get_theme_service),
                 svc: SettingsService = Depends(get_settings_service)):
    return themes.resolve_active(svc.get(), _now(request))


@router.get("/themes/{theme_id}", response_model=Theme)
def get_theme(theme_id: str, themes: ThemeService = Depends(get_theme_service)):
    return themes.get(theme_id)


@router.put("/settings/theme", response_model=UserSettings)
async def select_theme(body: ThemeSelect, request: Request, themes: ThemeService = Depends(get_theme_service),
                       svc: SettingsService = Depends(get_settings_service)):
    """Theme direkt am Display wechseln (ohne PIN). Schaltet den automatischen Wechsel aus."""
    changes = UserSettingsUpdate(theme=body.theme, auto_theme=False)
    _validate_theme_ids(themes, changes)
    user = svc.update(changes)
    await _publish_theme_if_changed(request, themes, user)
    return user


@router.get("/settings", response_model=UserSettings)
def get_user_settings(svc: SettingsService = Depends(get_settings_service)):
    return svc.get()


@router.put("/settings", response_model=UserSettings, dependencies=[Depends(require_admin)])
async def update_user_settings(changes: UserSettingsUpdate, request: Request,
                               themes: ThemeService = Depends(get_theme_service),
                               svc: SettingsService = Depends(get_settings_service)):
    _validate_theme_ids(themes, changes)
    user = svc.update(changes)
    await request.app.state.bus.publish("settings.changed", {})
    await _publish_theme_if_changed(request, themes, user)
    return user
