"""API-Datentransferobjekte (Request/Response)."""
import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.config import HomeLocation, NightMode, _check_hhmm

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date_or_datetime(value):
    """``2026-11-24`` → date (ganztägig), alles andere → datetime."""
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        if _DATE_ONLY.match(value):
            return date.fromisoformat(value)
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Ungültiges Datum/Zeitpunkt: {value!r}") from exc
    raise ValueError("Datum oder Zeitpunkt erwartet")


DateOrDateTime = Annotated[datetime | date, BeforeValidator(_parse_date_or_datetime)]


def _check_color(value: str | None) -> str | None:
    if value is not None and not HEX_COLOR.match(value):
        raise ValueError("Farbe im Format #RRGGBB erwartet")
    return value


class _ColorMixin(BaseModel):
    @field_validator("color", check_fields=False)
    @classmethod
    def _validate_color(cls, value: str | None) -> str | None:
        return _check_color(value)


# --- Familienmitglieder ---------------------------------------------------------------------

class MemberCreate(_ColorMixin):
    name: str = Field(min_length=1, max_length=60)
    color: str
    avatar: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class MemberUpdate(_ColorMixin):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = None
    avatar: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    color: str
    avatar: str | None
    sort_order: int


# --- Kalender & Konten ----------------------------------------------------------------------

class CalendarOut(BaseModel):
    id: int
    account_id: int
    provider: str
    name: str
    color: str | None
    read_only: bool
    visible: bool
    is_default: bool
    default_member_id: int | None


class CalendarCreate(_ColorMixin):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = None
    default_member_id: int | None = None


class CalendarUpdate(_ColorMixin):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = None
    visible: bool | None = None
    is_default: bool | None = None
    default_member_id: int | None = None


class AccountOut(BaseModel):
    id: int
    provider: str
    display_name: str
    last_sync: datetime | None
    last_error: str | None
    calendar_count: int


# --- Termine --------------------------------------------------------------------------------

class EventCreate(BaseModel):
    """Zeiten ohne Zeitzone werden als Ortszeit interpretiert. Ganztägig: Datum angeben,
    ``end`` exklusiv (Standard: Folgetag)."""

    calendar_id: int | None = None
    title: str = Field(min_length=1, max_length=300)
    start: DateOrDateTime
    end: DateOrDateTime | None = None
    all_day: bool = False
    timezone: str | None = None
    description: str | None = Field(default=None, max_length=10_000)
    location: str | None = Field(default=None, max_length=500)
    rrule: str | None = Field(default=None, max_length=500)
    member_ids: list[int] = Field(default_factory=list)
    category: str | None = Field(default=None, max_length=50)


class EventUpdate(BaseModel):
    calendar_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    start: DateOrDateTime | None = None
    end: DateOrDateTime | None = None
    all_day: bool | None = None
    timezone: str | None = None
    description: str | None = Field(default=None, max_length=10_000)
    location: str | None = Field(default=None, max_length=500)
    rrule: str | None = Field(default=None, max_length=500)
    member_ids: list[int] | None = None
    category: str | None = Field(default=None, max_length=50)


class EventOccurrence(BaseModel):
    """Ein konkretes Vorkommen (bei Serien eines von vielen)."""

    id: int
    occurrence_id: str
    calendar_id: int
    title: str
    description: str | None
    location: str | None
    start: datetime | date
    end: datetime | date
    all_day: bool
    timezone: str
    rrule: str | None
    recurring: bool
    member_ids: list[int]
    color: str | None
    category: str | None
    read_only: bool


class FamilyDay(BaseModel):
    date: date
    cells: dict[int, list[EventOccurrence]]
    unassigned: list[EventOccurrence]


class FamilyTable(BaseModel):
    members: list[MemberOut]
    days: list[FamilyDay]


# --- Einstellungen & Themes -----------------------------------------------------------------

ViewName = Literal["month", "week", "family"]


class UserSettings(BaseModel):
    """In der Weboberfläche änderbare Einstellungen (Standardwerte aus config.yaml)."""

    theme: str = "nordic"
    auto_theme: bool = False
    day_theme: str = "light"
    night_theme: str = "dark"
    day_starts: str = "07:00"
    night_starts: str = "19:00"
    default_view: ViewName = "week"
    week_starts_on: Literal["monday", "sunday"] = "monday"
    night_mode: NightMode = NightMode()
    home: HomeLocation = HomeLocation()
    activity_radius_km: float = Field(default=30, gt=0, le=500)

    @field_validator("day_starts", "night_starts")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        return _check_hhmm(value)


class UserSettingsUpdate(BaseModel):
    theme: str | None = None
    auto_theme: bool | None = None
    day_theme: str | None = None
    night_theme: str | None = None
    day_starts: str | None = None
    night_starts: str | None = None
    default_view: ViewName | None = None
    week_starts_on: Literal["monday", "sunday"] | None = None
    night_mode: NightMode | None = None
    home: HomeLocation | None = None
    activity_radius_km: float | None = Field(default=None, gt=0, le=500)


class ThemeFont(BaseModel):
    family: str = "Inter"
    scale: float = Field(default=1.0, ge=0.5, le=2.0)


REQUIRED_THEME_TOKENS = ("bg", "surface", "text", "text-muted", "accent", "border", "today", "weekend")


class Theme(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    mode: Literal["light", "dark", "eink"]
    tokens: dict[str, str]
    memberPalette: list[str] = Field(min_length=1)
    font: ThemeFont = ThemeFont()
    builtin: bool = True

    @field_validator("tokens")
    @classmethod
    def _validate_tokens(cls, tokens: dict[str, str]) -> dict[str, str]:
        missing = [t for t in REQUIRED_THEME_TOKENS if t not in tokens]
        if missing:
            raise ValueError(f"Fehlende Theme-Tokens: {', '.join(missing)}")
        for key, value in tokens.items():
            if not HEX_COLOR.match(value):
                raise ValueError(f"Token {key}: Farbe im Format #RRGGBB erwartet")
        return tokens


class ThemeSelect(BaseModel):
    theme: str


# --- Auth & Display -------------------------------------------------------------------------

class PinBody(BaseModel):
    pin: str


class ChangePinBody(BaseModel):
    current_pin: str
    new_pin: str


class AuthStatus(BaseModel):
    pin_set: bool
    authenticated: bool


class DisplayState(BaseModel):
    screen_on: bool
    brightness: int = Field(ge=0, le=100)
    night_active: bool
    hardware_backlight: bool


class DisplayUpdate(BaseModel):
    screen_on: bool | None = None
    brightness: int | None = Field(default=None, ge=0, le=100)
