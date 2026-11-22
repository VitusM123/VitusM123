"""Zwei-Wege-Synchronisation lokaler Termine mit externen Kalendern.

Ablauf je Kalender: Pull (Delta via sync_token) → Upsert/Soft-Delete → Push der Outbox
(Events mit pending_push=True) → Event-Bus "events.changed".
Konfliktregel (MVP): last write wins (updated/ETag), bei Gleichstand gewinnt Remote.

Status: Der Rahmen (Statusverwaltung, Sperre gegen parallele Läufe, Fehlerprotokoll pro Konto)
ist umgesetzt. Die Provider (Google, iCloud) folgen in Schritt 3 und 4.
"""
import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.core.events import EventBus
from app.core.timeutil import utcnow
from app.domain.models import Account, ProviderType
from app.providers.calendar.registry import PROVIDERS

log = logging.getLogger(__name__)


@dataclass
class SyncStatus:
    state: str = "idle"                # idle | running | error
    last_run: datetime | None = None
    last_error: str | None = None
    accounts_synced: int = 0

    def as_payload(self) -> dict:
        data = asdict(self)
        data["last_run"] = self.last_run.isoformat() if self.last_run else None
        return data


class SyncService:
    def __init__(self, engine: Engine, bus: EventBus) -> None:
        self.engine = engine
        self.bus = bus
        self.status = SyncStatus()
        self._lock = asyncio.Lock()

    async def sync_all(self) -> SyncStatus:
        if self._lock.locked():
            return self.status
        async with self._lock:
            self.status.state = "running"
            await self.bus.publish("sync.status", self.status.as_payload())
            synced, errors = 0, []
            with Session(self.engine) as session:
                accounts = session.exec(select(Account).where(Account.provider != ProviderType.LOCAL)).all()
                for account in accounts:
                    try:
                        if await self.sync_account(session, account):
                            synced += 1
                    except Exception as exc:  # ein Konto darf die anderen nicht blockieren
                        log.exception("Sync für Konto %s fehlgeschlagen", account.id)
                        account.last_error = str(exc)[:500]
                        session.add(account)
                        errors.append(f"{account.display_name}: {exc}")
                session.commit()
            self.status = SyncStatus(
                state="error" if errors else "idle", last_run=utcnow(),
                last_error="; ".join(errors) or None, accounts_synced=synced,
            )
            await self.bus.publish("sync.status", self.status.as_payload())
            if synced:
                await self.bus.publish("events.changed", {"reason": "sync"})
            return self.status

    async def sync_account(self, session: Session, account: Account) -> bool:
        """Synchronisiert ein Konto. Liefert False, wenn der Provider noch nicht verfügbar ist."""
        provider_cls = PROVIDERS.get(account.provider.value)
        if provider_cls is None or not getattr(provider_cls, "implemented", False):
            log.debug("Provider %s noch nicht implementiert – übersprungen", account.provider.value)
            return False
        raise NotImplementedError  # Schritt 3/4: Pull, Upsert, Outbox-Push
