"""Adapter: Google Calendar API v3.

Auth: OAuth2 Device Flow ("TV & Limited Input"). Der Code wird am Pi/Handy angezeigt.
Delta-Sync: events.list(syncToken=...). HTTP 410 erzwingt einen Voll-Resync.
"""
from app.providers.calendar.base import CalendarProvider


class GoogleCalendarProvider(CalendarProvider):
    provider_id = "google"

    async def start_device_flow(self) -> dict:
        """TODO: Liefert user_code + verification_url für die Anzeige."""
        raise NotImplementedError

    async def poll_device_flow(self, device_code: str) -> dict:
        """TODO: Pollt, bis der Nutzer bestätigt hat. Liefert die Tokens."""
        raise NotImplementedError

    # TODO: Methoden aus CalendarProvider implementieren
