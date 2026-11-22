"""Kalender, Termine, Familientabelle, manueller Sync."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.deps import get_calendar_service, require_admin
from app.schemas import (
    CalendarCreate,
    CalendarOut,
    CalendarUpdate,
    EventCreate,
    EventOccurrence,
    EventUpdate,
    FamilyTable,
)
from app.services.calendar_service import CalendarService

router = APIRouter(prefix="/api", tags=["calendar"])


async def _changed(request: Request, event_type: str = "events.changed", **payload) -> None:
    await request.app.state.bus.publish(event_type, payload)
    if event_type == "events.changed":
        request.app.state.sync.request_sync()   # Änderungen zügig zu Google/iCloud übertragen


# --- Kalender -------------------------------------------------------------------------------

@router.get("/calendars", response_model=list[CalendarOut])
def list_calendars(svc: CalendarService = Depends(get_calendar_service)):
    return svc.list_calendars()


@router.post("/calendars", response_model=CalendarOut, status_code=201, dependencies=[Depends(require_admin)])
async def create_calendar(data: CalendarCreate, request: Request,
                          svc: CalendarService = Depends(get_calendar_service)):
    cal = svc.create_local_calendar(data)
    await _changed(request, "calendars.changed")
    return cal


@router.put("/calendars/{calendar_id}", response_model=CalendarOut, dependencies=[Depends(require_admin)])
async def update_calendar(calendar_id: int, data: CalendarUpdate, request: Request,
                          svc: CalendarService = Depends(get_calendar_service)):
    cal = svc.update_calendar(calendar_id, data)
    await _changed(request, "calendars.changed")
    await _changed(request)
    return cal


@router.delete("/calendars/{calendar_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_calendar(calendar_id: int, request: Request, svc: CalendarService = Depends(get_calendar_service)):
    svc.delete_local_calendar(calendar_id)
    await _changed(request, "calendars.changed")
    await _changed(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Termine --------------------------------------------------------------------------------

@router.get("/events", response_model=list[EventOccurrence])
def list_events(
    start: datetime,
    end: datetime,
    members: list[int] | None = Query(default=None, description="Nur Termine dieser Mitglieder"),
    calendars: list[int] | None = Query(default=None, description="Nur diese Kalender (auch ausgeblendete)"),
    svc: CalendarService = Depends(get_calendar_service),
):
    """Alle Vorkommen im Zeitraum [start, end). Zeiten ohne Zeitzone gelten als Ortszeit."""
    return svc.list_occurrences(start, end, member_ids=members, calendar_ids=calendars)


@router.get("/events/{event_id}", response_model=EventOccurrence)
def get_event(event_id: int, svc: CalendarService = Depends(get_calendar_service)):
    return svc.get_event(event_id)


@router.post("/events", response_model=EventOccurrence, status_code=201)
async def create_event(data: EventCreate, request: Request, svc: CalendarService = Depends(get_calendar_service)):
    ev = svc.create_event(data)
    await _changed(request, event_id=ev.id)
    return svc.get_event(ev.id)


@router.put("/events/{event_id}", response_model=EventOccurrence)
async def update_event(
    event_id: int,
    data: EventUpdate,
    request: Request,
    occurrence_start: str | None = Query(default=None, description="Nur dieses Vorkommen einer Serie ändern"),
    svc: CalendarService = Depends(get_calendar_service),
):
    occ = svc.parse_occurrence_start(occurrence_start) if occurrence_start else None
    ev = svc.update_event(event_id, data, occ)
    await _changed(request, event_id=ev.id)
    return svc.get_event(ev.id)


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: int,
    request: Request,
    occurrence_start: str | None = Query(default=None, description="Nur dieses Vorkommen einer Serie löschen"),
    svc: CalendarService = Depends(get_calendar_service),
):
    occ = svc.parse_occurrence_start(occurrence_start) if occurrence_start else None
    svc.delete_event(event_id, occ)
    await _changed(request, event_id=event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/family-table", response_model=FamilyTable)
def family_table(
    start: date,
    days: int = Query(default=7, ge=1, le=62),
    svc: CalendarService = Depends(get_calendar_service),
):
    """Tabelle Tage × Familienmitglieder ab ``start`` für ``days`` Tage."""
    return svc.family_table(start, start + timedelta(days=days))


@router.post("/sync")
async def trigger_sync(request: Request):
    status_ = await request.app.state.sync.sync_all()
    return status_.as_payload()


@router.get("/sync")
def sync_status(request: Request):
    return request.app.state.sync.status.as_payload()
