"""Zwei-Wege-Synchronisation lokaler Termine mit externen Kalendern.

Ablauf je Konto:
1. Kalenderliste abgleichen (neue anlegen, entfernte löschen, Name/Farbe/Schreibrecht übernehmen)
2. Je Kalender: Änderungen holen (Delta über ``sync_token``; bei 410 Voll-Sync)
3. Änderungen anwenden – Serien/Einzeltermine zuerst, danach geänderte/abgesagte Vorkommen
4. Lokale Änderungen hochladen (Outbox: ``pending_push``)

Konfliktregel: Ist ein Termin lokal geändert (noch nicht hochgeladen) und remote ebenfalls,
gewinnt die jüngere Änderung (``updated`` remote gegen ``updated_at`` lokal).
"""
import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.config import Settings
from app.core.events import EventBus
from app.core.security import SecretBox
from app.core.timeutil import UTC, utcnow
from app.domain.models import Account, Calendar, Event, EventMember, FamilyMember, ProviderType
from app.providers.calendar.base import (
    AuthError,
    CalendarProvider,
    OutgoingEvent,
    ProviderError,
    RemoteEvent,
    RemoteNotFound,
    SyncTokenExpired,
)

log = logging.getLogger(__name__)
ProviderFactory = Callable[[Session, Account, httpx.AsyncClient], CalendarProvider | None]


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


@dataclass
class SyncStats:
    pulled: int = 0
    pushed: int = 0
    deleted: int = 0

    def add(self, other: "SyncStats") -> None:
        self.pulled += other.pulled
        self.pushed += other.pushed
        self.deleted += other.deleted


def load_credentials(secrets: SecretBox, account: Account) -> dict[str, Any]:
    if not account.credentials_encrypted:
        return {}
    return json.loads(secrets.decrypt(account.credentials_encrypted))


def store_credentials(secrets: SecretBox, account: Account, creds: dict[str, Any]) -> None:
    account.credentials_encrypted = secrets.encrypt(json.dumps(creds).encode())


class SyncService:
    def __init__(
        self,
        engine: Engine,
        bus: EventBus,
        settings: Settings | None = None,
        secrets: SecretBox | None = None,
        provider_factory: ProviderFactory | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.engine = engine
        self.bus = bus
        self.settings = settings
        self.secrets = secrets
        self.provider_factory = provider_factory
        self.http_transport = http_transport
        self.status = SyncStatus()
        self._lock = asyncio.Lock()
        self._debounce: asyncio.TimerHandle | None = None
        self.auto_sync = True       # in Tests abschaltbar

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.http_transport, timeout=30)

    def request_sync(self, delay: float = 2.0) -> None:
        """Sync nach lokalen Änderungen anstoßen (mehrere Änderungen werden gebündelt)."""
        if not self.auto_sync:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._debounce:
            self._debounce.cancel()
        self._debounce = loop.call_later(delay, lambda: loop.create_task(self.sync_all()))

    async def sync_all(self) -> SyncStatus:
        if self._lock.locked():
            return self.status
        async with self._lock:
            self.status.state = "running"
            await self.bus.publish("sync.status", self.status.as_payload())
            synced, errors, changed = 0, [], False
            with Session(self.engine) as session:
                ids = session.exec(select(Account.id).where(Account.provider != ProviderType.LOCAL)).all()
            for account_id in ids:
                try:
                    stats = await self.sync_account(account_id)
                    if stats is not None:
                        synced += 1
                        changed = changed or bool(stats.pulled or stats.pushed or stats.deleted)
                except Exception as exc:  # ein Konto darf die anderen nicht blockieren
                    log.exception("Sync für Konto %s fehlgeschlagen", account_id)
                    errors.append(str(exc))
            self.status = SyncStatus(
                state="error" if errors else "idle", last_run=utcnow(),
                last_error="; ".join(errors) or None, accounts_synced=synced,
            )
            await self.bus.publish("sync.status", self.status.as_payload())
            if changed:
                await self.bus.publish("events.changed", {"reason": "sync"})
                await self.bus.publish("calendars.changed", {})
            return self.status

    async def sync_account(self, account_id: int) -> SyncStats | None:
        """Synchronisiert ein Konto. ``None``, wenn für den Anbieter (noch) kein Provider existiert."""
        if self.provider_factory is None:
            return None
        async with self.http_client() as http:
            with Session(self.engine) as session:
                account = session.get(Account, account_id)
                if account is None:
                    return None
                try:
                    provider = self.provider_factory(session, account, http)
                    if provider is None:
                        return None
                    stats = await self._sync_account(session, account, provider)
                    account.last_sync = utcnow()
                    account.last_error = None
                    session.add(account)
                    session.commit()
                    return stats
                except (ProviderError, httpx.HTTPError) as exc:
                    session.rollback()
                    account = session.get(Account, account_id)
                    account.last_error = str(exc)[:500]
                    session.add(account)
                    session.commit()
                    raise

    # --- Kalenderliste ----------------------------------------------------------------------

    async def _sync_account(self, session: Session, account: Account, provider: CalendarProvider) -> SyncStats:
        remote_cals = await provider.list_calendars()
        local = {c.remote_id: c for c in session.exec(select(Calendar).where(Calendar.account_id == account.id))}
        for rc in remote_cals:
            cal = local.pop(rc.remote_id, None)
            if cal is None:
                cal = Calendar(account_id=account.id, remote_id=rc.remote_id, name=rc.name, color=rc.color,
                               visible=rc.selected, read_only=rc.read_only)
            else:
                cal.name, cal.read_only = rc.name, rc.read_only
                cal.color = cal.color or rc.color
                if cal.read_only and cal.is_default:
                    cal.is_default = False
            session.add(cal)
        for gone in local.values():           # remote entfernt → lokal entfernen
            self._delete_calendar(session, gone)
        session.commit()

        stats = SyncStats()
        for cal in session.exec(select(Calendar).where(Calendar.account_id == account.id)).all():
            stats.add(await self._sync_calendar(session, cal, provider))
        return stats

    def _delete_calendar(self, session: Session, cal: Calendar) -> None:
        events = session.exec(select(Event).where(Event.calendar_id == cal.id)).all()
        self._hard_delete(session, events)
        session.delete(cal)
        session.flush()

    # --- Termine ----------------------------------------------------------------------------

    async def _sync_calendar(self, session: Session, cal: Calendar, provider: CalendarProvider) -> SyncStats:
        stats = SyncStats()
        try:
            changes = await provider.fetch_changes(cal.remote_id, cal.sync_token)
        except SyncTokenExpired:
            log.info("Sync-Token für %s abgelaufen – Voll-Sync", cal.name)
            changes = await provider.fetch_changes(cal.remote_id, None)

        masters = [e for e in changes.events if not e.recurring_remote_id]
        instances = [e for e in changes.events if e.recurring_remote_id]
        for remote in masters:
            stats.add(self._apply_event(session, cal, remote))
        session.flush()
        for remote in instances:
            stats.add(self._apply_instance(session, cal, remote))
        self._prune_instances(session, cal, masters, instances)

        if changes.full:
            seen = {e.remote_id for e in changes.events if not e.cancelled}
            stale = session.exec(select(Event).where(
                Event.calendar_id == cal.id, Event.remote_id.is_not(None), Event.pending_push == False,  # noqa: E712
                Event.remote_id.not_in(seen) if seen else Event.remote_id.is_not(None),
            )).all()
            # Remote abgesagte Vorkommen (deleted=True) bleiben als Ausnahme erhalten
            stale = [e for e in stale if not (e.deleted and e.recurrence_master_id)]
            stats.deleted += len(stale)
            self._hard_delete(session, stale)

        cal.sync_token = changes.next_sync_token
        session.add(cal)
        session.commit()

        if not cal.read_only:
            stats.pushed += await self._push(session, cal, provider)
        return stats

    def _apply_event(self, session: Session, cal: Calendar, remote: RemoteEvent) -> SyncStats:
        stats = SyncStats()
        local = session.exec(select(Event).where(Event.calendar_id == cal.id,
                                                 Event.remote_id == remote.remote_id)).first()
        if remote.cancelled:
            if local:
                self._hard_delete(session, [local])
                stats.deleted += 1
            return stats
        if local and self._local_wins(local, remote):
            return stats
        if remote.start is None or remote.end is None:
            return stats
        ev = local or Event(calendar_id=cal.id, remote_id=remote.remote_id, title=remote.title,
                            start=remote.start, end=remote.end)
        self._copy_fields(ev, remote)
        ev.rrule = remote.rrule
        ev.exdates = sorted({x.astimezone(UTC).isoformat() for x in remote.exdates}) if remote.rrule else []
        session.add(ev)
        session.flush()
        if remote.member_ids is not None:
            self._set_members(session, ev.id, remote.member_ids)
        stats.pulled += 1
        return stats

    def _apply_instance(self, session: Session, cal: Calendar, remote: RemoteEvent) -> SyncStats:
        stats = SyncStats()
        master = session.exec(select(Event).where(Event.calendar_id == cal.id,
                                                  Event.remote_id == remote.recurring_remote_id)).first()
        if master is None:
            # Serie unbekannt (z. B. außerhalb des Abrufs) → wie Einzeltermin behandeln
            remote.recurring_remote_id = None
            return self._apply_event(session, cal, remote)

        local = session.exec(select(Event).where(Event.calendar_id == cal.id,
                                                 Event.remote_id == remote.remote_id)).first()
        if local is None and remote.original_start is not None:
            local = session.exec(select(Event).where(Event.recurrence_master_id == master.id,
                                                     Event.original_start == remote.original_start)).first()
        if local and self._local_wins(local, remote):
            return stats
        original = remote.original_start or (local.original_start if local else None)
        if original is None:
            return stats
        if local is None:
            local = Event(calendar_id=cal.id, title=master.title, start=remote.start or original,
                          end=remote.end or original + (master.end - master.start),
                          recurrence_master_id=master.id, original_start=original)
        local.remote_id = remote.remote_id
        local.etag = remote.etag
        local.pending_push = False
        if remote.cancelled:
            local.deleted = True        # abgesagtes Vorkommen bleibt als Ausnahme erhalten
            stats.deleted += 1
        else:
            local.deleted = False
            self._copy_fields(local, remote)
            stats.pulled += 1
        session.add(local)
        session.flush()
        if not remote.cancelled:
            ids = remote.member_ids
            if ids is None:   # ohne Angabe: Personen der Serie übernehmen
                ids = list(session.exec(select(EventMember.member_id).where(EventMember.event_id == master.id)))
            self._set_members(session, local.id, ids)
        return stats

    def _prune_instances(self, session: Session, cal: Calendar, masters: list[RemoteEvent],
                         instances: list[RemoteEvent]) -> None:
        """CalDAV liefert Serien immer vollständig: Einzeländerungen, die remote nicht mehr existieren,
        werden lokal entfernt (sofern nicht lokal geändert)."""
        present = {i.remote_id for i in instances}
        for remote in masters:
            if not remote.complete_instances or remote.cancelled:
                continue
            master = session.exec(select(Event).where(Event.calendar_id == cal.id,
                                                      Event.remote_id == remote.remote_id)).first()
            if master is None or master.pending_push:
                continue
            gone = session.exec(select(Event).where(
                Event.recurrence_master_id == master.id, Event.pending_push == False,  # noqa: E712
                Event.deleted == False,  # noqa: E712
            )).all()
            self._hard_delete(session, [e for e in gone if e.remote_id not in present])

    @staticmethod
    def _local_wins(local: Event, remote: RemoteEvent) -> bool:
        if not local.pending_push:
            return False
        if remote.updated is None:
            return True
        return local.updated_at >= remote.updated

    @staticmethod
    def _copy_fields(ev: Event, remote: RemoteEvent) -> None:
        if remote.uid:
            ev.remote_uid = remote.uid
        ev.title = remote.title
        ev.description = remote.description
        ev.location = remote.location
        if remote.start and remote.end:
            ev.start, ev.end = remote.start, remote.end
        ev.all_day = remote.all_day
        if remote.timezone:
            ev.timezone = remote.timezone
        ev.etag = remote.etag
        ev.deleted = False
        ev.pending_push = False
        ev.updated_at = remote.updated or utcnow()

    @staticmethod
    def _set_members(session: Session, event_id: int, member_ids: list[int]) -> None:
        valid = set(session.exec(select(FamilyMember.id)))
        for link in session.exec(select(EventMember).where(EventMember.event_id == event_id)):
            session.delete(link)
        session.flush()
        for member_id in dict.fromkeys(member_ids):
            if member_id in valid:
                session.add(EventMember(event_id=event_id, member_id=member_id))

    @staticmethod
    def _hard_delete(session: Session, events: list[Event]) -> None:
        ids = [e.id for e in events if e.id is not None]
        if not ids:
            return
        children = session.exec(select(Event).where(Event.recurrence_master_id.in_(ids),
                                                    Event.id.not_in(ids))).all()
        all_events = [*children, *events]
        all_ids = [e.id for e in all_events]
        for link in session.exec(select(EventMember).where(EventMember.event_id.in_(all_ids))):
            session.delete(link)
        session.flush()
        for e in children:
            session.delete(e)
        session.flush()
        for e in events:
            session.delete(e)
        session.flush()

    # --- Hochladen (Outbox) -----------------------------------------------------------------

    def _outgoing(self, session: Session, ev: Event, master: Event | None) -> OutgoingEvent:
        members = list(session.exec(select(EventMember.member_id).where(EventMember.event_id == ev.id)))
        return OutgoingEvent(
            uid=ev.remote_uid,
            title=ev.title, start=ev.start, end=ev.end, all_day=ev.all_day, timezone=ev.timezone,
            description=ev.description, location=ev.location, rrule=ev.rrule,
            exdates=[datetime.fromisoformat(x) for x in ev.exdates], member_ids=members,
            recurring_remote_id=master.remote_id if master else None,
            original_start=ev.original_start,
        )

    async def _push(self, session: Session, cal: Calendar, provider: CalendarProvider) -> int:
        if getattr(provider, "whole_resource", False):
            return await self._push_resources(session, cal, provider)
        pending = session.exec(select(Event).where(Event.calendar_id == cal.id,
                                                   Event.pending_push == True)).all()  # noqa: E712
        # Reihenfolge: Serien/Einzeltermine → Einzelvorkommen → Löschungen
        order = sorted(pending, key=lambda e: (e.deleted, e.recurrence_master_id is not None))
        pushed = 0
        for ev in order:
            try:
                if ev.deleted:
                    if ev.remote_id:
                        await provider.delete_event(cal.remote_id, ev.remote_id)
                    if ev.recurrence_master_id is not None:
                        ev.pending_push = False      # bleibt als Ausnahme erhalten
                        session.add(ev)
                    else:
                        self._hard_delete(session, [ev])
                elif ev.recurrence_master_id is not None:
                    master = session.get(Event, ev.recurrence_master_id)
                    if master is None or not master.remote_id:
                        continue                     # Serie ist noch nicht hochgeladen
                    rid = ev.remote_id or provider.instance_id(master.remote_id, ev.original_start, ev.all_day)
                    ev.etag = await provider.update_event(cal.remote_id, rid, self._outgoing(session, ev, master))
                    ev.remote_id = rid
                else:
                    data = self._outgoing(session, ev, None)
                    if ev.remote_id:
                        try:
                            ev.etag = await provider.update_event(cal.remote_id, ev.remote_id, data)
                        except RemoteNotFound:      # remote gelöscht → neu anlegen
                            ev.remote_id, ev.etag = await provider.create_event(cal.remote_id, data)
                    else:
                        ev.remote_id, ev.etag = await provider.create_event(cal.remote_id, data)
                if not ev.deleted or ev.recurrence_master_id is not None:
                    ev.pending_push = False
                    session.add(ev)
                session.commit()
                pushed += 1
            except AuthError:
                raise
            except ProviderError as exc:
                session.rollback()
                log.warning("Termin %s konnte nicht übertragen werden: %s", ev.id, exc)
        return pushed

    async def _push_resources(self, session: Session, cal: Calendar, provider: CalendarProvider) -> int:
        """CalDAV: Serie und alle Einzelvorkommen werden gemeinsam als eine Ressource geschrieben."""
        pending = session.exec(select(Event).where(Event.calendar_id == cal.id,
                                                   Event.pending_push == True)).all()  # noqa: E712
        roots: dict[int, Event] = {}
        for ev in pending:
            root = ev if ev.recurrence_master_id is None else session.get(Event, ev.recurrence_master_id)
            if root is None:
                continue
            if ev is not root and ev.deleted:
                # abgesagtes Einzelvorkommen: wird über EXDATE der Serie übertragen
                ev.pending_push = False
                session.add(ev)
            roots[root.id] = root
        pushed = 0
        for root in roots.values():
            try:
                if root.deleted:
                    if root.remote_id:
                        await provider.delete_event(cal.remote_id, root.remote_id)
                    self._hard_delete(session, [root])
                else:
                    overrides = session.exec(select(Event).where(Event.recurrence_master_id == root.id,
                                                                 Event.deleted == False)).all()  # noqa: E712
                    if not root.remote_uid:
                        root.remote_uid = str(uuid.uuid4())
                    data = self._outgoing(session, root, None)
                    data.instances = [self._outgoing(session, o, root) for o in overrides
                                      if o.original_start is not None] if root.rrule else []
                    if root.remote_id:
                        try:
                            root.etag = await provider.update_event(cal.remote_id, root.remote_id, data)
                        except RemoteNotFound:
                            root.remote_id, root.etag = await provider.create_event(cal.remote_id, data)
                    else:
                        root.remote_id, root.etag = await provider.create_event(cal.remote_id, data)
                    root.pending_push = False
                    session.add(root)
                    for o in overrides:
                        o.remote_id = provider.instance_id(root.remote_id, o.original_start, o.all_day)
                        o.pending_push = False
                        session.add(o)
                session.commit()
                pushed += 1
            except AuthError:
                raise
            except ProviderError as exc:
                session.rollback()
                log.warning("Termin %s konnte nicht übertragen werden: %s", root.id, exc)
        return pushed
