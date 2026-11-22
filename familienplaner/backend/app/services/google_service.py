"""Google-Anbindung: Client-Konfiguration, Anmeldeablauf (OAuth mit PKCE), Provider-Erzeugung."""
import secrets as pysecrets
import time
from dataclasses import dataclass

import httpx
from sqlmodel import Session, select

from app.config import Settings
from app.core.security import SecretBox
from app.domain.models import Account, ProviderType, Setting
from app.providers.calendar.base import AuthError
from app.providers.calendar.google import (
    GoogleCalendarProvider,
    build_auth_url,
    exchange_code,
    parse_redirect,
    pkce_pair,
)
from app.services.errors import ConflictError, ValidationError
from app.services.sync_service import load_credentials, store_credentials

CLIENT_SETTING_KEY = "google_client"
PENDING_TTL = 15 * 60


@dataclass
class GoogleClient:
    client_id: str
    client_secret: str
    redirect_uri: str
    source: str            # "config" | "settings"


def default_redirect_uri(settings: Settings) -> str:
    return settings.google.redirect_uri or f"http://127.0.0.1:{settings.server.port}/api/accounts/google/callback"


def get_client(session: Session, settings: Settings, box: SecretBox) -> GoogleClient | None:
    redirect = default_redirect_uri(settings)
    if settings.google.client_id and settings.google.client_secret:
        return GoogleClient(settings.google.client_id, settings.google.client_secret, redirect, "config")
    row = session.get(Setting, CLIENT_SETTING_KEY)
    if row and row.value.get("client_id"):
        secret = box.decrypt(row.value["client_secret"].encode()).decode()
        return GoogleClient(row.value["client_id"], secret, redirect, "settings")
    return None


def set_client(session: Session, box: SecretBox, client_id: str, client_secret: str) -> None:
    client_id, client_secret = client_id.strip(), client_secret.strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise ValidationError("Die Client-ID endet normalerweise auf .apps.googleusercontent.com")
    if len(client_secret) < 10:
        raise ValidationError("Bitte das Client-Secret angeben")
    value = {"client_id": client_id, "client_secret": box.encrypt(client_secret.encode()).decode()}
    row = session.get(Setting, CLIENT_SETTING_KEY) or Setting(key=CLIENT_SETTING_KEY)
    row.value = value
    session.add(row)
    session.commit()


class PendingAuth:
    """Offene Anmeldevorgänge (state → PKCE-Verifier), nur im Speicher und 15 min gültig."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[str, str, float]] = {}

    def create(self, redirect_uri: str) -> tuple[str, str]:
        self._cleanup()
        state = pysecrets.token_urlsafe(24)
        verifier, challenge = pkce_pair()
        self._items[state] = (verifier, redirect_uri, time.time())
        return state, challenge

    def pop(self, state: str | None) -> tuple[str, str]:
        self._cleanup()
        if state is None:
            # Nur Code eingefügt: eindeutig nur, wenn genau ein Vorgang offen ist
            if len(self._items) != 1:
                raise ValidationError("Bitte die vollständige Adresse aus der Adresszeile einfügen")
            state = next(iter(self._items))
        item = self._items.pop(state, None)
        if item is None:
            raise ValidationError("Anmeldevorgang unbekannt oder abgelaufen – bitte erneut starten")
        return item[0], item[1]

    def _cleanup(self) -> None:
        now = time.time()
        for key in [k for k, (_, _, t) in self._items.items() if now - t > PENDING_TTL]:
            del self._items[key]


def start_auth(session: Session, settings: Settings, box: SecretBox, pending: PendingAuth) -> dict:
    client = get_client(session, settings, box)
    if client is None:
        raise ConflictError("Google-Zugang ist noch nicht eingerichtet (Client-ID/Secret fehlen)")
    state, challenge = pending.create(client.redirect_uri)
    return {"auth_url": build_auth_url(client.client_id, client.redirect_uri, state, challenge),
            "redirect_uri": client.redirect_uri}


async def complete_auth(session: Session, settings: Settings, box: SecretBox, pending: PendingAuth,
                        http: httpx.AsyncClient, url_or_code: str, state: str | None = None) -> Account:
    code, parsed_state = parse_redirect(url_or_code)
    verifier, redirect_uri = pending.pop(state or parsed_state)
    client = get_client(session, settings, box)
    if client is None:
        raise ConflictError("Google-Zugang ist nicht eingerichtet")
    creds = await exchange_code(http, client.client_id, client.client_secret, code, redirect_uri, verifier)

    provider = GoogleCalendarProvider(http, creds, client.client_id, client.client_secret,
                                      default_timezone=settings.locale.timezone)
    calendars = await provider.list_calendars()
    primary = next((c for c in calendars if c.primary), calendars[0] if calendars else None)
    name = primary.remote_id if primary else "Google"

    account = session.exec(select(Account).where(Account.provider == ProviderType.GOOGLE,
                                                 Account.display_name == name)).first()
    if account is None:
        account = Account(provider=ProviderType.GOOGLE, display_name=name)
    store_credentials(box, account, provider.creds)
    account.last_error = None
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def make_provider_factory(settings: Settings, box: SecretBox):
    """Erzeugt zu einem Konto den passenden Provider (None = Anbieter noch nicht unterstützt)."""

    def factory(session: Session, account: Account, http: httpx.AsyncClient):
        if account.provider != ProviderType.GOOGLE:
            return None   # iCloud folgt in Schritt 4
        client = get_client(session, settings, box)
        if client is None:
            raise AuthError("Google-Zugang ist nicht eingerichtet (Client-ID/Secret fehlen)")
        creds = load_credentials(box, account)

        def on_credentials(updated: dict) -> None:
            store_credentials(box, account, updated)
            session.add(account)
            session.commit()

        return GoogleCalendarProvider(http, creds, client.client_id, client.client_secret,
                                      on_credentials=on_credentials, default_timezone=settings.locale.timezone)

    return factory
