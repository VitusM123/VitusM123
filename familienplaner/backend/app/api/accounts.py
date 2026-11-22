"""Verknüpfte Kalenderkonten. Google (Device Flow) und iCloud (CalDAV) folgen in Schritt 3/4."""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel import Session, func, select

from app.core.db import get_session
from app.core.deps import require_admin
from app.domain.models import Account, Calendar, Event, EventMember, ProviderType
from app.schemas import AccountOut
from app.services.errors import ForbiddenError, NotFoundError

router = APIRouter(prefix="/api/accounts", tags=["accounts"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AccountOut])
def list_accounts(session: Session = Depends(get_session)):
    stmt = select(Calendar.account_id, func.count(Calendar.id)).group_by(Calendar.account_id)
    counts = dict(session.exec(stmt).all())
    return [
        AccountOut(id=a.id, provider=a.provider.value, display_name=a.display_name, last_sync=a.last_sync,
                   last_error=a.last_error, calendar_count=counts.get(a.id, 0))
        for a in session.exec(select(Account).order_by(Account.id))
    ]


@router.delete("/{account_id}", status_code=204)
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
    session.delete(account)
    session.commit()
    await request.app.state.bus.publish("calendars.changed", {})
    await request.app.state.bus.publish("events.changed", {"reason": "account_removed"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
