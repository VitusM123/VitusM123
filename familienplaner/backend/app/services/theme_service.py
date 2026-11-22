"""Themes: mitgelieferte (app/themes) und eigene (<datenverzeichnis>/themes) JSON-Dateien.

Eigene Themes mit gleicher ``id`` überschreiben mitgelieferte. Ungültige Dateien werden
übersprungen und protokolliert, damit ein Tippfehler nicht die Anzeige lahmlegt.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from app.core.timeutil import in_time_range, parse_hhmm
from app.schemas import Theme, UserSettings
from app.services.errors import NotFoundError

log = logging.getLogger(__name__)
BUILTIN_DIR = Path(__file__).resolve().parents[1] / "themes"
FALLBACK_THEME_ID = "light"


class ThemeService:
    def __init__(self, custom_dir: Path | None = None) -> None:
        self.custom_dir = custom_dir

    def _load_dir(self, directory: Path, builtin: bool) -> dict[str, Theme]:
        themes: dict[str, Theme] = {}
        if not directory or not directory.is_dir():
            return themes
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["builtin"] = builtin
                theme = Theme.model_validate(data)
                themes[theme.id] = theme
            except (OSError, ValueError) as exc:
                log.warning("Theme %s ungültig und übersprungen: %s", path, exc)
        return themes

    def list_themes(self) -> list[Theme]:
        themes = self._load_dir(BUILTIN_DIR, builtin=True)
        if self.custom_dir:
            themes.update(self._load_dir(self.custom_dir, builtin=False))
        # E-Ink-Themes ans Ende, sonst alphabetisch
        return sorted(themes.values(), key=lambda t: (t.mode == "eink", t.name.lower()))

    def get(self, theme_id: str) -> Theme:
        for theme in self.list_themes():
            if theme.id == theme_id:
                return theme
        raise NotFoundError(f"Theme „{theme_id}“ nicht gefunden")

    def exists(self, theme_id: str) -> bool:
        return any(t.id == theme_id for t in self.list_themes())

    def resolve_active_id(self, user: UserSettings, now_local: datetime) -> str:
        """Aktives Theme – bei automatischem Wechsel abhängig von der Uhrzeit."""
        if user.auto_theme:
            day = in_time_range(now_local.time(), parse_hhmm(user.day_starts), parse_hhmm(user.night_starts))
            return user.day_theme if day else user.night_theme
        return user.theme

    def resolve_active(self, user: UserSettings, now_local: datetime) -> Theme:
        theme_id = self.resolve_active_id(user, now_local)
        try:
            return self.get(theme_id)
        except NotFoundError:
            log.warning("Aktives Theme %s fehlt – verwende %s", theme_id, FALLBACK_THEME_ID)
            return self.get(FALLBACK_THEME_ID)
