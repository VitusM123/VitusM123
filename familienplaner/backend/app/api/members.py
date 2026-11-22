"""Familienmitglieder. Lesen ohne PIN, Ändern nur mit Admin-PIN."""
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlmodel import Session

from app.core.db import get_session
from app.core.deps import get_member_service, require_admin
from app.schemas import MemberCreate, MemberOut, MemberUpdate
from app.services.calendar_service import CalendarService
from app.services.member_service import MemberService

router = APIRouter(prefix="/api/members", tags=["members"])


async def _changed(request: Request) -> None:
    await request.app.state.bus.publish("members.changed", {})
    await request.app.state.bus.publish("events.changed", {"reason": "members"})


@router.get("", response_model=list[MemberOut])
def list_members(svc: MemberService = Depends(get_member_service)):
    return svc.list_members()


@router.post("", response_model=MemberOut, status_code=201, dependencies=[Depends(require_admin)])
async def create_member(data: MemberCreate, request: Request, svc: MemberService = Depends(get_member_service)):
    member = svc.create(data)
    await _changed(request)
    return member


@router.put("/order", response_model=list[MemberOut], dependencies=[Depends(require_admin)])
async def reorder_members(member_ids: list[int], request: Request, svc: MemberService = Depends(get_member_service)):
    members = svc.reorder(member_ids)
    await _changed(request)
    return members


@router.put("/{member_id}", response_model=MemberOut, dependencies=[Depends(require_admin)])
async def update_member(member_id: int, data: MemberUpdate, request: Request,
                        svc: MemberService = Depends(get_member_service)):
    member = svc.update(member_id, data)
    await _changed(request)
    return member


class MemberCalendars(BaseModel):
    calendar_ids: list[int]


@router.put("/{member_id}/calendars", response_model=MemberCalendars, dependencies=[Depends(require_admin)])
async def set_member_calendars(member_id: int, body: MemberCalendars, request: Request,
                               session: Session = Depends(get_session)):
    """Übersicht nach Person: Kalender festlegen, die dieser Person gehören."""
    ids = CalendarService(session, request.app.state.settings).set_member_calendars(member_id, body.calendar_ids)
    await request.app.state.bus.publish("calendars.changed", {})
    await request.app.state.bus.publish("events.changed", {"reason": "calendar_members"})
    return MemberCalendars(calendar_ids=ids)


@router.delete("/{member_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_member(member_id: int, request: Request, svc: MemberService = Depends(get_member_service)):
    svc.delete(member_id)
    await _changed(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
