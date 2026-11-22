"""Adapter: Apple iCloud über CalDAV (https://caldav.icloud.com).

Anmeldung mit Apple-ID und **app-spezifischem Passwort** (appleid.apple.com → Anmeldung und
Sicherheit → App-spezifische Passwörter). Das normale Apple-ID-Passwort funktioniert nicht.
"""
from app.providers.calendar.caldav import CalDAVProvider

ICLOUD_CALDAV_URL = "https://caldav.icloud.com"


class ICloudCalendarProvider(CalDAVProvider):
    provider_id = "icloud"

    def __init__(self, http, username: str, password: str, home_url: str | None = None,
                 default_timezone: str = "Europe/Berlin", base_url: str = ICLOUD_CALDAV_URL) -> None:
        super().__init__(http, base_url, username, password, home_url, default_timezone)
