"""Verknüpfte Kalenderkonten: Google verbinden (OAuth), synchronisieren, trennen."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from app.config import Settings
from app.core.db import get_session
from app.core.deps import get_settings, require_admin
from app.domain.models import Account, Calendar, Event, EventMember, ProviderType
from app.providers.calendar.base import ProviderError
from app.schemas import AccountOut
from app.services import google_service
from app.services.errors import ForbiddenError, NotFoundError, ValidationError

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
admin = [Depends(require_admin)]


class GoogleConfigIn(BaseModel):
    client_id: str = Field(min_length=10, max_length=300)
    client_secret: str = Field(min_length=10, max_length=300)


class GoogleConfigOut(BaseModel):
    configured: bool
    source: str | None
    client_id: str | None
    redirect_uri: str


class CompleteIn(BaseModel):
    url: str = Field(min_length=4, max_length=4000, description="Adresse aus der Adresszeile nach der Anmeldung")


def _account_out(session: Session, a: Account) -> AccountOut:
    count = session.exec(select(func.count(Calendar.id)).where(Calendar.account_id == a.id)).one()
    return AccountOut(id=a.id, provider=a.provider.value, display_name=a.display_name, last_sync=a.last_sync,
                      last_error=a.last_error, calendar_count=count)


@router.get("", response_model=list[AccountOut], dependencies=admin)
def list_accounts(session: Session = Depends(get_session)):
    return [_account_out(session, a) for a in session.exec(select(Account).order_by(Account.id))]


# --- Google ---------------------------------------------------------------------------------

@router.get("/google/config", response_model=GoogleConfigOut, dependencies=admin)
def google_config(request: Request, session: Session = Depends(get_session),
                  settings: Settings = Depends(get_settings)):
    client = google_service.get_client(session, settings, request.app.state.secrets)
    return GoogleConfigOut(
        configured=client is not None, source=client.source if client else None,
        client_id=client.client_id if client else None,
        redirect_uri=google_service.default_redirect_uri(settings),
    )


@router.put("/google/config", response_model=GoogleConfigOut, dependencies=admin)
def set_google_config(body: GoogleConfigIn, request: Request, session: Session = Depends(get_session),
                      settings: Settings = Depends(get_settings)):
    if settings.google.client_id:
        raise ValidationError("Der Google-Zugang ist in der config.yaml festgelegt und wird dort geändert")
    google_service.set_client(session, request.app.state.secrets, body.client_id, body.client_secret)
    return google_config(request, session, settings)


@router.post("/google/start", dependencies=admin)
def google_start(request: Request, session: Session = Depends(get_session),
                 settings: Settings = Depends(get_settings)):
    """Liefert die Google-Anmeldeadresse."""
    return google_service.start_auth(session, settings, request.app.state.secrets, request.app.state.google_pending)


async def _complete(request: Request, session: Session, settings: Settings, url: str,
                    state: str | None = None) -> Account:
    async with request.app.state.sync.http_client() as http:
        account = await google_service.complete_auth(
            session, settings, request.app.state.secrets, request.app.state.google_pending, http, url, state)
    request.app.state.sync.request_sync(0.1)
    await request.app.state.bus.publish("calendars.changed", {})
    return account


@router.post("/google/complete", response_model=AccountOut, dependencies=admin)
async def google_complete(body: CompleteIn, request: Request, session: Session = Depends(get_session),
                          settings: Settings = Depends(get_settings)):
    """Anmeldung abschließen mit der kopierten Weiterleitungsadresse (Anmeldung am Handy/Laptop)."""
    try:
        account = await _complete(request, session, settings, body.url)
    except ProviderError as exc:
        raise ValidationError(str(exc)) from exc
    return _account_out(session, account)


@router.get("/google/callback", include_in_schema=False)
async def google_callback(request: Request, state: str | None = None, code: str | None = None,
                          error: str | None = None, session: Session = Depends(get_session),
                          settings: Settings = Depends(get_settings)):
    """Weiterleitungsziel von Google, wenn die Anmeldung direkt am Pi erfolgt.
    Kein Admin-Cookie nötig: ``state`` belegt, dass der Vorgang vom Admin gestartet wurde."""
    if error or not code:
        return RedirectResponse(f"/?google_error={quote(error or 'abgebrochen')}#/settings")
    try:
        await _complete(request, session, settings, f"?code={quote(code)}&state={quote(state or '')}", state)
    except (ProviderError, ValidationError) as exc:
        return RedirectResponse(f"/?google_error={quote(str(exc))}#/settings")
    return RedirectResponse("/?google=connected#/settings")


# --- Allgemein ------------------------------------------------------------------------------

@router.post("/{account_id}/sync", dependencies=admin)
async def sync_account(account_id: int, request: Request, session: Session = Depends(get_session)):
    if session.get(Account, account_id) is None:
        raise NotFoundError(f"Konto {account_id} nicht gefunden")
    status_ = await request.app.state.sync.sync_all()
    return status_.as_payload()


@router.delete("/{account_id}", status_code=204, dependencies=admin)
async def delete_account(account_id: int, request: Request, session: Session = Depends(get_session)):
    """Entfernt ein externes Konto samt lokal gespiegelter Kalender (remote bleibt alles erhalten)."""
    account = session.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Konto {account_id} nicht gefunden")
    if account.provider == ProviderType.LOCAL:
        raise ForbiddenError("Das lokale Konto kann nicht entfernt werden")
    cal_ids = list(session.exec(select(Calendar.id).where(Calendar.account_id == account_id)))
    if cal_ids:
        event_ids = list(session.exec(select(Event.id).where(Event.calendar_id.in_(cal_ids))))
        if event_ids:
            for link in session.exec(select(EventMember).where(EventMember.event_id.in_(event_ids))):
                session.delete(link)
            session.flush()
            # Einzeländerungen zuerst (Fremdschlüssel auf die Serie), dann die übrigen Termine
            for only_overrides in (True, False):
                master = Event.recurrence_master_id
                cond = master.is_not(None) if only_overrides else master.is_(None)
                for ev in session.exec(select(Event).where(Event.id.in_(event_ids), cond)):
                    session.delete(ev)
                session.flush()
        for cal in session.exec(select(Calendar).where(Calendar.id.in_(cal_ids))):
            session.delete(cal)
        session.flush()   # Kalender vor dem Konto löschen (Fremdschlüssel)
    session.delete(account)
    session.commit()
    await request.app.state.bus.publish("calendars.changed", {})
    await request.app.state.bus.publish("events.changed", {"reason": "account_removed"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
