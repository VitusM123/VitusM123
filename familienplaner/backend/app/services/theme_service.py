"""Themes: Laden der Theme-JSONs, aktives Theme, optionaler Tag/Nacht-Wechsel."""


class ThemeService:
    def list_themes(self) -> list[dict]:
        raise NotImplementedError

    def get_active_theme(self) -> dict:
        raise NotImplementedError

    def set_active_theme(self, theme_id: str) -> None:
        raise NotImplementedError
