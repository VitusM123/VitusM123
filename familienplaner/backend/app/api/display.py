"""Display: Bildschirm an/aus, Helligkeit (am Gerät ohne PIN bedienbar)."""
from fastapi import APIRouter, Request

from app.schemas import DisplayState, DisplayUpdate

router = APIRouter(prefix="/api/display", tags=["display"])


async def _publish(request: Request, state: DisplayState) -> DisplayState:
    await request.app.state.bus.publish("display.changed", state.model_dump())
    return state


@router.get("", response_model=DisplayState)
def get_display(request: Request):
    return request.app.state.display.state()


@router.put("", response_model=DisplayState)
async def update_display(body: DisplayUpdate, request: Request):
    return await _publish(request, request.app.state.display.set(body.screen_on, body.brightness))


@router.post("/wake", response_model=DisplayState)
async def wake(request: Request):
    """Wird vom Frontend bei Berührung des abgedunkelten Bildschirms aufgerufen."""
    return await _publish(request, request.app.state.display.set(screen_on=True))
