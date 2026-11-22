"""Erzeugt zu einem Konto den passenden Kalender-Provider."""
import httpx
from sqlmodel import Session

from app.config import Settings
from app.core.security import SecretBox
from app.domain.models import Account, ProviderType
from app.providers.calendar.base import AuthError, CalendarProvider
from app.providers.calendar.google import GoogleCalendarProvider
from app.providers.calendar.icloud import ICLOUD_CALDAV_URL, ICloudCalendarProvider
from app.services.google_service import get_client
from app.services.sync_service import load_credentials, store_credentials


def make_provider_factory(settings: Settings, box: SecretBox):
    tz = settings.locale.timezone

    def factory(session: Session, account: Account, http: httpx.AsyncClient) -> CalendarProvider | None:
        creds = load_credentials(box, account)
        if account.provider == ProviderType.GOOGLE:
            client = get_client(session, settings, box)
            if client is None:
                raise AuthError("Google-Zugang ist nicht eingerichtet (Client-ID/Secret fehlen)")

            def on_credentials(updated: dict) -> None:
                store_credentials(box, account, updated)
                session.add(account)
                session.commit()

            return GoogleCalendarProvider(http, creds, client.client_id, client.client_secret,
                                          on_credentials=on_credentials, default_timezone=tz)
        if account.provider == ProviderType.ICLOUD:
            if not creds.get("username"):
                raise AuthError("Zugangsdaten fehlen – bitte iCloud neu verbinden")
            return ICloudCalendarProvider(http, creds["username"], creds["password"], creds.get("home_url"),
                                          default_timezone=tz, base_url=creds.get("base_url", ICLOUD_CALDAV_URL))
        return None

    return factory
