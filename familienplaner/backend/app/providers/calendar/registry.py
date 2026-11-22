"""Registry: provider_id -> CalendarProvider-Klasse."""
from app.providers.calendar.base import CalendarProvider
from app.providers.calendar.google import GoogleCalendarProvider
from app.providers.calendar.icloud import ICloudCalendarProvider

PROVIDERS: dict[str, type[CalendarProvider]] = {
    GoogleCalendarProvider.provider_id: GoogleCalendarProvider,
    ICloudCalendarProvider.provider_id: ICloudCalendarProvider,
}
