"""Endpunkte: CRUD für Familienmitglieder."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/members", tags=["members"])
