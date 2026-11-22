"""Endpunkte: GET/PUT /api/display (Helligkeit, Nachtmodus), POST /eink/refresh. WebSocket /ws für Live-Updates."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/display", tags=["display"])
