"""Konfiguration.

Reihenfolge (höchste Priorität zuerst):
1. Argumente an ``Settings(...)`` (Tests)
2. Umgebungsvariablen mit Präfix ``FP_`` (verschachtelt über ``__``, z. B. ``FP_DISPLAY__THEME=dark``)
3. YAML-Datei (Pfad aus ``FP_CONFIG_FILE``, Standard ``/etc/familienplaner/config.yaml``)
4. Standardwerte unten (für die Entwicklung: Daten unter ``./data``)
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

DEFAULT_CONFIG_FILE = Path("/etc/familienplaner/config.yaml")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _check_hhmm(value: str) -> str:
    if not _TIME_RE.match(value):
        raise ValueError(f"Uhrzeit im Format HH:MM erwartet, erhalten: {value!r}")
    return value


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    # Verzeichnis mit dem gebauten Frontend; None = automatisch ../frontend/dist suchen
    frontend_dist: Path | None = None


class DatabaseSettings(BaseModel):
    path: Path = Path("data/familienplaner.db")
    backup_dir: Path = Path("data/backups")
    backup_keep: int = 14


class SecuritySettings(BaseModel):
    secret_key_file: Path = Path("data/secret.key")
    session_hours: int = 12


class LocaleSettings(BaseModel):
    language: str = "de"
    timezone: str = "Europe/Berlin"
    week_starts_on: Literal["monday", "sunday"] = "monday"


class NightMode(BaseModel):
    enabled: bool = True
    off: str = "22:30"
    on: str = "06:30"

    @field_validator("off", "on")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        return _check_hhmm(value)


class EInkSettings(BaseModel):
    driver: str = "waveshare_13in3e"
    layout: Literal["week", "family"] = "week"
    refresh_minutes: int = 15


class DisplaySettings(BaseModel):
    mode: Literal["lcd", "eink"] = "lcd"
    default_view: Literal["month", "week", "family"] = "week"
    theme: str = "nordic"
    night_mode: NightMode = NightMode()
    eink: EInkSettings = EInkSettings()
    # z. B. /sys/class/backlight/10-0045 (offizielles Pi-Touch-Display). None = nur Software-Abdunklung
    backlight_path: Path | None = None


class SyncSettings(BaseModel):
    interval_minutes: int = 5
    past_days: int = 30
    future_days: int = 365


class GoogleSettings(BaseModel):
    # OAuth-Client vom Typ „Desktop-App“. Alternativ in der Weboberfläche hinterlegen.
    client_id: str = ""
    client_secret: str = ""
    # Standard: http://127.0.0.1:<port>/api/accounts/google/callback
    redirect_uri: str | None = None


class HomeLocation(BaseModel):
    address: str = ""
    lat: float | None = None
    lon: float | None = None


class ActivitySettings(BaseModel):
    home: HomeLocation = HomeLocation()
    default_radius_km: float = 30
    refresh_hours: int = 12
    geocoder: dict[str, Any] = Field(default_factory=lambda: {"provider": "nominatim", "user_agent": "familienplaner"})
    sources: list[dict[str, Any]] = Field(default_factory=list)


class _YamlSource(PydanticBaseSettingsSource):
    """Liest die YAML-Konfigurationsdatei (falls vorhanden)."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = Path(os.environ.get("FP_CONFIG_FILE", DEFAULT_CONFIG_FILE))
        if not path.is_file():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path}: Konfiguration muss ein YAML-Mapping sein")
        return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FP_", env_nested_delimiter="__", extra="ignore")

    server: ServerSettings = ServerSettings()
    database: DatabaseSettings = DatabaseSettings()
    security: SecuritySettings = SecuritySettings()
    locale: LocaleSettings = LocaleSettings()
    display: DisplaySettings = DisplaySettings()
    sync: SyncSettings = SyncSettings()
    google: GoogleSettings = GoogleSettings()
    activities: ActivitySettings = ActivitySettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, env_settings, _YamlSource(settings_cls)

    @property
    def data_dir(self) -> Path:
        return self.database.path.parent

    @property
    def custom_themes_dir(self) -> Path:
        return self.data_dir / "themes"

    def resolve_frontend_dist(self) -> Path | None:
        if self.server.frontend_dist is not None:
            return self.server.frontend_dist if self.server.frontend_dist.is_dir() else None
        candidate = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        return candidate if candidate.is_dir() else None


@lru_cache
def load_settings() -> Settings:
    return Settings()
