"""Endpunkte: GET/POST /api/events, PUT/DELETE /api/events/{id}, GET/PUT /api/calendars, POST /api/sync"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["calendar"])
