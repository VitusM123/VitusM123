"""Interner Event-Bus. Services publizieren, der WebSocket-Hub leitet an Clients weiter.

Event-Typen: "events.changed", "sync.status", "theme.changed", "settings.changed"
"""
from typing import Any, Awaitable, Callable

Handler = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus:
    def subscribe(self, handler: Handler) -> None:
        raise NotImplementedError

    async def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        raise NotImplementedError


bus = EventBus()
