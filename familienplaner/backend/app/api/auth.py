"""Admin-PIN: Ersteinrichtung, Anmeldung, Abmeldung, Änderung."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from app.config import Settings
from app.core.db import get_session
from app.core.deps import get_settings, is_admin, require_admin
from app.core.security import (
    SESSION_COOKIE,
    create_session_token,
    get_pin_record,
    set_pin,
    validate_pin_format,
    verify_pin,
)
from app.schemas import AuthStatus, ChangePinBody, PinBody
from app.services.errors import ConflictError, ValidationError

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _issue_cookie(response: Response, request: Request, session: Session, settings: Settings) -> None:
    record = get_pin_record(session)
    token = create_session_token(request.app.state.secrets.signing_key, record["hash"],
                                 settings.security.session_hours)
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.security.session_hours * 3600,
                        httponly=True, samesite="strict")


@router.get("/status", response_model=AuthStatus)
def auth_status(request: Request, session: Session = Depends(get_session)):
    pin_set = get_pin_record(session) is not None
    return AuthStatus(pin_set=pin_set, authenticated=pin_set and is_admin(request, session))


@router.post("/setup", response_model=AuthStatus)
def setup_pin(body: PinBody, request: Request, response: Response,
              session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    """Erste PIN festlegen (nur möglich, solange noch keine PIN existiert)."""
    if get_pin_record(session) is not None:
        raise ConflictError("Es ist bereits eine PIN gesetzt")
    try:
        set_pin(session, body.pin)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    _issue_cookie(response, request, session, settings)
    return AuthStatus(pin_set=True, authenticated=True)


@router.post("/login", response_model=AuthStatus)
def login(body: PinBody, request: Request, response: Response,
          session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    throttle = request.app.state.login_throttle
    client = _client(request)
    retry = throttle.retry_after(client)
    if retry:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Zu viele Fehlversuche. Bitte {retry} s warten.",
                            headers={"Retry-After": str(retry)})
    if get_pin_record(session) is None:
        raise ConflictError("Noch keine PIN festgelegt")
    if not verify_pin(session, body.pin):
        throttle.register_failure(client)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falsche PIN")
    throttle.register_success(client)
    _issue_cookie(response, request, session, settings)
    return AuthStatus(pin_set=True, authenticated=True)


@router.post("/logout", response_model=AuthStatus)
def logout(response: Response, session: Session = Depends(get_session)):
    response.delete_cookie(SESSION_COOKIE)
    return AuthStatus(pin_set=get_pin_record(session) is not None, authenticated=False)


@router.post("/change-pin", response_model=AuthStatus, dependencies=[Depends(require_admin)])
def change_pin(body: ChangePinBody, request: Request, response: Response,
               session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if not verify_pin(session, body.current_pin):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Aktuelle PIN ist falsch")
    try:
        validate_pin_format(body.new_pin)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    set_pin(session, body.new_pin)
    _issue_cookie(response, request, session, settings)  # alte Sitzungen sind damit ungültig
    return AuthStatus(pin_set=True, authenticated=True)
