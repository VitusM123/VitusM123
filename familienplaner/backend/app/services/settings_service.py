"""In der Weboberfläche änderbare Einstellungen (Tabelle ``setting``, Schlüssel ``app``).

Werte, die noch nie geändert wurden, kommen aus der config.yaml.
"""
from pydantic import ValidationError as PydanticValidationError
from sqlmodel import Session

from app.config import Settings
from app.domain.models import Setting
from app.schemas import UserSettings, UserSettingsUpdate
from app.services.errors import ValidationError

SETTINGS_KEY = "app"


def defaults_from_config(settings: Settings) -> UserSettings:
    return UserSettings(
        theme=settings.display.theme,
        default_view=settings.display.default_view,
        week_starts_on=settings.locale.week_starts_on,
        night_mode=settings.display.night_mode,
        home=settings.activities.home,
        activity_radius_km=settings.activities.default_radius_km,
    )


class SettingsService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def get(self) -> UserSettings:
        base = defaults_from_config(self.settings).model_dump(mode="json")
        row = self.session.get(Setting, SETTINGS_KEY)
        if row:
            base.update(row.value)
        return UserSettings.model_validate(base)

    def update(self, changes: UserSettingsUpdate) -> UserSettings:
        current = self.get().model_dump(mode="json")
        current.update(changes.model_dump(mode="json", exclude_unset=True, exclude_none=True))
        try:
            validated = UserSettings.model_validate(current)
        except PydanticValidationError as exc:
            raise ValidationError("; ".join(e["msg"] for e in exc.errors())) from exc
        row = self.session.get(Setting, SETTINGS_KEY) or Setting(key=SETTINGS_KEY)
        row.value = validated.model_dump(mode="json")
        self.session.add(row)
        self.session.commit()
        return validated
