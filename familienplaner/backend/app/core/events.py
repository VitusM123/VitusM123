"""Interner Event-Bus. Services publizieren Ereignisse, verbundene WebSocket-Clients
(Kiosk, Smartphone) erhalten sie als JSON ``{"type": ..., "payload": ...}``.

Event-Typen: ``events.changed``, ``calendars.changed``, ``members.changed``, ``sync.status``,
``theme.changed``, ``settings.changed``, ``display.changed``
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)
Handler = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[Handler] = []
        self._sockets: set[WebSocket] = set()

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._sockets.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._sockets.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._sockets)

    async def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        payload = payload or {}
        for handler in list(self._handlers):
            try:
                await handler(event_type, payload)
            except Exception:  # ein fehlerhafter Handler darf andere nicht blockieren
                log.exception("Event-Handler für %s fehlgeschlagen", event_type)
        message = {"type": event_type, "payload": payload}
        sockets = list(self._sockets)
        results = await asyncio.gather(*(ws.send_json(message) for ws in sockets), return_exceptions=True)
        for ws, result in zip(sockets, results, strict=True):
            if isinstance(result, Exception):
                self.disconnect(ws)
