"""Konfiguration aus config.yaml + Umgebungsvariablen (Präfix FP_)."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class NightMode(BaseModel):
    enabled: bool = True
    off: str = "22:30"
    on: str = "06:30"


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


class SyncSettings(BaseModel):
    interval_minutes: int = 5
    past_days: int = 30
    future_days: int = 365


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FP_", env_nested_delimiter="__")

    config_file: Path = Path("/etc/familienplaner/config.yaml")
    database_path: Path = Path("/var/lib/familienplaner/familienplaner.db")
    secret_key_file: Path = Path("/etc/familienplaner/secret.key")
    timezone: str = "Europe/Berlin"
    display: DisplaySettings = DisplaySettings()
    sync: SyncSettings = SyncSettings()


def load_settings() -> Settings:
    """TODO: YAML einlesen und mit Umgebungsvariablen zusammenführen."""
    raise NotImplementedError
