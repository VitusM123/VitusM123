"""Endpunkte: POST /search, POST /{id}/add-to-calendar, GET/POST/PUT/DELETE /sources."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/activities", tags=["activities"])
