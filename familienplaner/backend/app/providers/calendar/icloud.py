"""Adapter: Apple iCloud über CalDAV (https://caldav.icloud.com).

Auth: Apple-ID + app-spezifisches Passwort (appleid.apple.com).
Delta-Sync: CTag/ETag-Vergleich bzw. sync-collection (RFC 6578).
"""
from app.providers.calendar.base import CalendarProvider


class ICloudCalendarProvider(CalendarProvider):
    provider_id = "icloud"
    CALDAV_URL = "https://caldav.icloud.com"

    # TODO: Methoden aus CalendarProvider implementieren
