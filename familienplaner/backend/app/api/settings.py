"""Endpunkte: GET /api/themes, GET/PUT /api/settings, POST /api/auth/pin."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["settings"])
