"""iCloud-Anbindung (CalDAV): Konto mit Apple-ID und app-spezifischem Passwort verbinden."""
import re

import httpx
from sqlmodel import Session, select

from app.config import Settings
from app.core.security import SecretBox
from app.domain.models import Account, ProviderType
from app.providers.calendar.icloud import ICLOUD_CALDAV_URL, ICloudCalendarProvider
from app.services.errors import ValidationError
from app.services.sync_service import store_credentials

APP_PASSWORD = re.compile(r"^[a-z]{4}-[a-z]{4}-[a-z]{4}-[a-z]{4}$")


async def connect(session: Session, settings: Settings, box: SecretBox, http: httpx.AsyncClient,
                  apple_id: str, app_password: str, server_url: str | None = None) -> Account:
    apple_id = apple_id.strip()
    password = app_password.strip().replace(" ", "")
    base_url = (server_url or "").strip() or ICLOUD_CALDAV_URL
    if "@" not in apple_id:
        raise ValidationError("Bitte die Apple-ID (E-Mail-Adresse) angeben")
    if base_url == ICLOUD_CALDAV_URL and not APP_PASSWORD.match(password.lower()):
        raise ValidationError("Bitte ein app-spezifisches Passwort im Format xxxx-xxxx-xxxx-xxxx verwenden "
                              "(nicht das normale Apple-ID-Passwort)")
    provider = ICloudCalendarProvider(http, apple_id, password, default_timezone=settings.locale.timezone,
                                      base_url=base_url)
    home = await provider.discover()          # prüft gleichzeitig die Zugangsdaten
    await provider.list_calendars()

    account = session.exec(select(Account).where(Account.provider == ProviderType.ICLOUD,
                                                 Account.display_name == apple_id)).first()
    if account is None:
        account = Account(provider=ProviderType.ICLOUD, display_name=apple_id)
    store_credentials(box, account, {"username": apple_id, "password": password, "home_url": home,
                                     "base_url": base_url})
    account.last_error = None
    session.add(account)
    session.commit()
    session.refresh(account)
    return account
