"""FastAPI-Dependencies: Settings, Services, Admin-Schutz."""
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.config import Settings
from app.core.db import get_session
from app.core.security import SESSION_COOKIE, get_pin_record, verify_session_token
from app.services.calendar_service import CalendarService
from app.services.member_service import MemberService
from app.services.settings_service import SettingsService
from app.services.theme_service import ThemeService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_calendar_service(session: Session = Depends(get_session),
                         settings: Settings = Depends(get_settings)) -> CalendarService:
    return CalendarService(session, settings)


def get_member_service(session: Session = Depends(get_session)) -> MemberService:
    return MemberService(session)


def get_settings_service(session: Session = Depends(get_session),
                         settings: Settings = Depends(get_settings)) -> SettingsService:
    return SettingsService(session, settings)


def get_theme_service(request: Request) -> ThemeService:
    return request.app.state.themes


def is_admin(request: Request, session: Session) -> bool:
    record = get_pin_record(session)
    if record is None:
        return True  # Ersteinrichtung: noch keine PIN gesetzt
    return verify_session_token(
        request.app.state.secrets.signing_key, record["hash"], request.cookies.get(SESSION_COOKIE)
    )


def require_admin(request: Request, session: Session = Depends(get_session)) -> None:
    if not is_admin(request, session):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin-PIN erforderlich")
