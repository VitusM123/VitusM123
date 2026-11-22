"""Systemendpunkte: Healthcheck, Basisinformationen für das Frontend, WebSocket."""
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from app import __version__

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health(request: Request):
    return {"status": "ok", "version": __version__, "ws_clients": request.app.state.bus.client_count}


@router.get("/api/info")
def info(request: Request):
    s = request.app.state.settings
    return {
        "version": __version__,
        "timezone": s.locale.timezone,
        "language": s.locale.language,
        "display_mode": s.display.mode,
    }


@router.websocket("/ws")
async def websocket(ws: WebSocket):
    bus = ws.app.state.bus
    await bus.connect(ws)
    try:
        while True:
            await ws.receive_text()  # Clients senden nur Keepalives
    except WebSocketDisconnect:
        pass
    finally:
        bus.disconnect(ws)
