"""Endpunkte: POST /google/device-code, POST /google/poll, POST /icloud, DELETE /{id}. PIN-geschützt."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
