"""Freizeitaktivitäten: Umkreissuche, Übernahme in den Kalender, Quellenverwaltung."""
from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel import Session

from app.core.db import get_session
from app.core.deps import require_admin
from app.schemas import (
    ActivitySearch,
    ActivitySearchResult,
    ActivitySourceIn,
    ActivitySourceOut,
    ActivitySourceUpdate,
    AddToCalendar,
    EventOccurrence,
    GeocodeIn,
    SearchCenter,
)
from app.services.activity_service import ActivityService
from app.services.calendar_service import CalendarService
from app.services.errors import ValidationError

router = APIRouter(prefix="/api/activities", tags=["activities"])
admin = [Depends(require_admin)]


def _svc(request: Request) -> ActivityService:
    return request.app.state.activities


@router.post("/search", response_model=ActivitySearchResult)
async def search(body: ActivitySearch, request: Request, session: Session = Depends(get_session)):
    return await _svc(request).search(session, body)


@router.post("/{activity_id}/add-to-calendar", response_model=EventOccurrence, status_code=201)
async def add_to_calendar(activity_id: int, body: AddToCalendar, request: Request,
                          session: Session = Depends(get_session)):
    ev = _svc(request).add_to_calendar(session, activity_id, body)
    await request.app.state.bus.publish("events.changed", {"event_id": ev.id})
    request.app.state.sync.request_sync()
    return CalendarService(session, request.app.state.settings).get_event(ev.id)


@router.post("/geocode", response_model=SearchCenter)
async def geocode(body: GeocodeIn, request: Request, session: Session = Depends(get_session)):
    """Adresse → Koordinaten (z. B. für den Wohnort in den Einstellungen)."""
    svc = _svc(request)
    async with svc.http_client() as http:
        point = await svc.geo.geocode(session, http, body.address)
    if point is None:
        raise ValidationError(f"Ort „{body.address}“ nicht gefunden")
    return SearchCenter(lat=point.lat, lon=point.lon, label=body.address.strip())


# --- Quellen --------------------------------------------------------------------------------

@router.get("/sources", response_model=list[ActivitySourceOut])
def list_sources(request: Request, session: Session = Depends(get_session)):
    return _svc(request).list_sources(session)


@router.post("/sources", response_model=ActivitySourceOut, status_code=201, dependencies=admin)
async def create_source(body: ActivitySourceIn, request: Request, session: Session = Depends(get_session)):
    out = _svc(request).create_source(session, body)
    await _svc(request).refresh_all(only_source=out.id)
    session.expire_all()
    return next(s for s in _svc(request).list_sources(session) if s.id == out.id)


@router.post("/sources/test", dependencies=admin)
async def test_source(body: ActivitySourceIn, request: Request):
    """Quelle probeweise abrufen, ohne zu speichern."""
    found = await _svc(request).test_source(body)
    return {
        "count": len(found),
        "sample": [{"title": c.title, "start": c.start.isoformat(), "all_day": c.all_day,
                    "venue": c.venue, "address": c.address} for c in found[:8]],
    }


@router.put("/sources/{source_id}", response_model=ActivitySourceOut, dependencies=admin)
def update_source(source_id: int, body: ActivitySourceUpdate, request: Request,
                  session: Session = Depends(get_session)):
    return _svc(request).update_source(session, source_id, body)


@router.delete("/sources/{source_id}", status_code=204, dependencies=admin)
def delete_source(source_id: int, request: Request, session: Session = Depends(get_session)):
    _svc(request).delete_source(session, source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/refresh", dependencies=admin)
async def refresh(request: Request):
    """Alle aktiven Quellen jetzt abrufen."""
    results = await _svc(request).refresh_all()
    return [{"source_id": r.source_id, "name": r.name, "count": r.count, "error": r.error} for r in results]
