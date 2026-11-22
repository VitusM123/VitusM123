"""Kalender und Termine: Abfragen für Monats-/Wochen-/Familienansicht, Anlegen/Ändern/Löschen.

Änderungen an Terminen in externen Kalendern (Google/iCloud) werden mit ``pending_push``
markiert (Outbox) und vom SyncService übertragen. Gelöschte externe Termine bleiben als
Grabstein (``deleted=True``) erhalten, bis der Sync sie entfernt hat.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.config import Settings
from app.core.timeutil import UTC, date_to_utc, ensure_aware, local_day_bounds, utc_to_date, utcnow
from app.domain.models import Account, Calendar, Event, EventMember, FamilyMember, ProviderType
from app.schemas import (
    CalendarCreate,
    CalendarOut,
    CalendarUpdate,
    EventCreate,
    EventOccurrence,
    EventUpdate,
    FamilyDay,
    FamilyTable,
    MemberOut,
)
from app.services import recurrence
from app.services.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.services.member_service import MemberService

MAX_WINDOW_DAYS = 400
MAX_FAMILY_TABLE_DAYS = 62


def ensure_default_calendar(session: Session) -> None:
    """Sorgt dafür, dass genau ein beschreibbarer Kalender Standard ist (z. B. nachdem der bisherige
    Standardkalender mit seinem Konto entfernt wurde). Lokale Kalender werden bevorzugt."""
    if session.exec(select(Calendar).where(Calendar.is_default == True)).first():  # noqa: E712
        return
    candidates = session.exec(
        select(Calendar, Account.provider).join(Account).where(Calendar.read_only == False)  # noqa: E712
        .order_by(Calendar.id)
    ).all()
    if not candidates:
        return
    cal = next((c for c, p in candidates if p == ProviderType.LOCAL), candidates[0][0])
    cal.is_default = True
    session.add(cal)


class CalendarService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.tz = ZoneInfo(settings.locale.timezone)

    # --- Kalender ---------------------------------------------------------------------------

    def _calendar_out(self, cal: Calendar, provider: ProviderType) -> CalendarOut:
        return CalendarOut(
            id=cal.id, account_id=cal.account_id, provider=provider.value, name=cal.name, color=cal.color,
            read_only=cal.read_only, visible=cal.visible, is_default=cal.is_default,
            default_member_id=cal.default_member_id,
        )

    def list_calendars(self) -> list[CalendarOut]:
        rows = self.session.exec(
            select(Calendar, Account.provider).join(Account).order_by(Account.id, Calendar.name)
        ).all()
        return [self._calendar_out(cal, provider) for cal, provider in rows]

    def get_calendar(self, calendar_id: int) -> Calendar:
        cal = self.session.get(Calendar, calendar_id)
        if cal is None:
            raise NotFoundError(f"Kalender {calendar_id} nicht gefunden")
        return cal

    def _provider_of(self, cal: Calendar) -> ProviderType:
        return self.session.get(Account, cal.account_id).provider

    def default_calendar(self) -> Calendar:
        cal = self.session.exec(
            select(Calendar).where(Calendar.is_default == True, Calendar.read_only == False)  # noqa: E712
        ).first()
        if cal is None:
            cal = self.session.exec(select(Calendar).where(Calendar.read_only == False)).first()  # noqa: E712
        if cal is None:
            raise NotFoundError("Kein beschreibbarer Kalender vorhanden")
        return cal

    def _local_account(self) -> Account:
        account = self.session.exec(select(Account).where(Account.provider == ProviderType.LOCAL)).first()
        if account is None:
            account = Account(provider=ProviderType.LOCAL, display_name="Lokal")
            self.session.add(account)
            self.session.flush()
        return account

    def create_local_calendar(self, data: CalendarCreate) -> CalendarOut:
        if data.default_member_id is not None:
            MemberService(self.session).ensure_exist([data.default_member_id])
        cal = Calendar(
            account_id=self._local_account().id, name=data.name.strip(), color=data.color,
            default_member_id=data.default_member_id,
        )
        self.session.add(cal)
        self.session.commit()
        self.session.refresh(cal)
        return self._calendar_out(cal, ProviderType.LOCAL)

    def update_calendar(self, calendar_id: int, data: CalendarUpdate) -> CalendarOut:
        cal = self.get_calendar(calendar_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("default_member_id") is not None:
            MemberService(self.session).ensure_exist([changes["default_member_id"]])
        if changes.get("is_default"):
            if cal.read_only:
                raise ValidationError("Ein schreibgeschützter Kalender kann nicht Standard sein")
            for other in self.session.exec(select(Calendar).where(Calendar.is_default == True)):  # noqa: E712
                other.is_default = False
                self.session.add(other)
        for key, value in changes.items():
            if key in ("name", "visible", "is_default") and value is None:
                continue
            setattr(cal, key, value)
        self.session.add(cal)
        self.session.commit()
        self.session.refresh(cal)
        return self._calendar_out(cal, self._provider_of(cal))

    def delete_local_calendar(self, calendar_id: int) -> None:
        cal = self.get_calendar(calendar_id)
        if self._provider_of(cal) != ProviderType.LOCAL:
            raise ForbiddenError("Externe Kalender werden über das zugehörige Konto entfernt")
        local_count = len(self.session.exec(
            select(Calendar.id).join(Account).where(Account.provider == ProviderType.LOCAL)
        ).all())
        if local_count <= 1:
            raise ConflictError("Der letzte lokale Kalender kann nicht gelöscht werden")
        events = self.session.exec(select(Event).where(Event.calendar_id == calendar_id)).all()
        self._hard_delete_events(events)
        was_default = cal.is_default
        self.session.delete(cal)
        self.session.flush()
        if was_default:
            replacement = self.session.exec(select(Calendar).where(Calendar.read_only == False)).first()  # noqa: E712
            if replacement:
                replacement.is_default = True
                self.session.add(replacement)
        self.session.commit()

    # --- Termine lesen ----------------------------------------------------------------------

    def _check_window(self, start: datetime, end: datetime, max_days: int = MAX_WINDOW_DAYS) -> None:
        if end <= start:
            raise ValidationError("Das Ende des Zeitraums muss nach dem Beginn liegen")
        if end - start > timedelta(days=max_days):
            raise ValidationError(f"Zeitraum darf höchstens {max_days} Tage umfassen")

    def list_occurrences(
        self,
        start: datetime,
        end: datetime,
        member_ids: list[int] | None = None,
        calendar_ids: list[int] | None = None,
    ) -> list[EventOccurrence]:
        start, end = ensure_aware(start, self.tz), ensure_aware(end, self.tz)
        self._check_window(start, end)
        # Puffer von einem Tag, weil ganztägige Termine Datumssemantik haben
        q_start, q_end = start - timedelta(days=1), end + timedelta(days=1)

        stmt = (
            select(Event, Calendar)
            .join(Calendar)
            .where(
                Event.deleted == False,  # noqa: E712
                Event.start < q_end,
                or_(Event.rrule.is_not(None), Event.end > q_start),
            )
        )
        if calendar_ids:
            stmt = stmt.where(Calendar.id.in_(calendar_ids))
        else:
            stmt = stmt.where(Calendar.visible == True)  # noqa: E712
        rows = self.session.exec(stmt).all()

        master_ids = [ev.id for ev, _ in rows if ev.rrule]
        # Vorkommen, die durch Einzeländerungen ersetzt oder abgesagt wurden
        overridden: dict[int, set[datetime]] = defaultdict(set)
        if master_ids:
            for master_id, original in self.session.exec(
                select(Event.recurrence_master_id, Event.original_start).where(
                    Event.recurrence_master_id.in_(master_ids)
                )
            ):
                if original is not None:
                    overridden[master_id].add(original)
        # Einzeländerungen, deren Serie gelöscht ist, nicht anzeigen
        override_master_ids = {ev.recurrence_master_id for ev, _ in rows if ev.recurrence_master_id}
        deleted_masters = set()
        if override_master_ids:
            deleted_masters = set(self.session.exec(
                select(Event.id).where(Event.id.in_(override_master_ids), Event.deleted == True)  # noqa: E712
            ))

        members_by_event = self._members_for([ev.id for ev, _ in rows])
        result: list[EventOccurrence] = []
        for ev, cal in rows:
            if ev.recurrence_master_id in deleted_masters:
                continue
            excluded = set(overridden.get(ev.id, set()))
            excluded.update(datetime.fromisoformat(x) for x in ev.exdates)
            spans = recurrence.expand(
                start=ev.start, end=ev.end, rrule=ev.rrule, all_day=ev.all_day, tz_name=ev.timezone,
                window_start=start, window_end=end, display_tz=self.tz, excluded=excluded,
            )
            if not spans:
                continue
            resolved = members_by_event.get(ev.id) or ([cal.default_member_id] if cal.default_member_id else [])
            if member_ids and not set(resolved) & set(member_ids):
                continue
            for occ_start, occ_end in spans:
                result.append(self._occurrence(ev, cal, occ_start, occ_end, resolved, cal.read_only))
        result.sort(key=self._sort_key)
        return result

    def get_event(self, event_id: int) -> EventOccurrence:
        ev = self._get_event(event_id)
        cal = self.get_calendar(ev.calendar_id)
        resolved = self._members_for([ev.id]).get(ev.id) or (
            [cal.default_member_id] if cal.default_member_id else []
        )
        return self._occurrence(ev, cal, ev.start, ev.end, resolved, cal.read_only)

    def family_table(self, start_date: date, end_date: date) -> FamilyTable:
        """Tage (Zeilen) × Familienmitglieder (Spalten). ``end_date`` ist exklusiv."""
        if end_date <= start_date:
            raise ValidationError("Das Enddatum muss nach dem Startdatum liegen")
        if (end_date - start_date).days > MAX_FAMILY_TABLE_DAYS:
            raise ValidationError(f"Höchstens {MAX_FAMILY_TABLE_DAYS} Tage")
        window_start = local_day_bounds(start_date, self.tz)[0]
        window_end = local_day_bounds(end_date - timedelta(days=1), self.tz)[1]
        members = MemberService(self.session).list_members()
        member_ids = {m.id for m in members}

        days: dict[date, FamilyDay] = {}
        d = start_date
        while d < end_date:
            days[d] = FamilyDay(date=d, cells={m.id: [] for m in members}, unassigned=[])
            d += timedelta(days=1)

        for occ in self.list_occurrences(window_start, window_end):
            for day in self._local_dates(occ):
                if day not in days:
                    continue
                targets = [m for m in occ.member_ids if m in member_ids]
                if not targets:
                    days[day].unassigned.append(occ)
                for m in targets:
                    days[day].cells[m].append(occ)
        return FamilyTable(
            members=[MemberOut.model_validate(m) for m in members], days=list(days.values())
        )

    # --- Termine schreiben ------------------------------------------------------------------

    def create_event(self, data: EventCreate) -> Event:
        cal = self.get_calendar(data.calendar_id) if data.calendar_id else self.default_calendar()
        self._ensure_writable(cal)
        tz_name = self._validate_tz(data.timezone)
        start, end = self._normalize_times(data.start, data.end, data.all_day, None)
        rrule = recurrence.validate_rrule(data.rrule, start) if data.rrule else None
        MemberService(self.session).ensure_exist(data.member_ids)

        ev = Event(
            calendar_id=cal.id, title=data.title.strip(), description=data.description, location=data.location,
            start=start, end=end, all_day=data.all_day, timezone=tz_name, rrule=rrule, category=data.category,
            pending_push=self._is_remote(cal),
        )
        self.session.add(ev)
        self.session.flush()
        self._set_members(ev.id, data.member_ids)
        self.session.commit()
        self.session.refresh(ev)
        return ev

    def parse_occurrence_start(self, value: str) -> datetime:
        """Vorkommen-Beginn aus der API: Datum (ganztägig, ``2026-11-22``) oder Zeitpunkt (ISO 8601)."""
        try:
            if len(value) == 10:
                return date_to_utc(date.fromisoformat(value))
            return ensure_aware(datetime.fromisoformat(value.replace("Z", "+00:00")), self.tz).astimezone(UTC)
        except ValueError as exc:
            raise ValidationError(f"Ungültiger Vorkommen-Zeitpunkt: {value!r}") from exc

    def update_event(self, event_id: int, data: EventUpdate, occurrence_start: datetime | None = None) -> Event:
        ev = self._get_event(event_id)
        if occurrence_start is not None:
            if not ev.rrule:
                raise ValidationError("occurrence_start ist nur bei wiederkehrenden Terminen erlaubt")
            if "rrule" in data.model_fields_set and data.rrule:
                raise ValidationError("Ein Einzelvorkommen kann keine eigene Wiederholung haben")
            ev = self._get_or_create_override(ev, occurrence_start.astimezone(UTC))

        cal = self.get_calendar(ev.calendar_id)
        self._ensure_writable(cal)
        fields = data.model_fields_set

        if "calendar_id" in fields and data.calendar_id and data.calendar_id != ev.calendar_id:
            if ev.recurrence_master_id is not None:
                raise ValidationError("Einzelvorkommen können nicht in einen anderen Kalender verschoben werden")
            target = self.get_calendar(data.calendar_id)
            self._ensure_writable(target)
            self._move_event(ev, cal, target)
            cal = target

        # Zeiten
        new_all_day = data.all_day if data.all_day is not None else ev.all_day
        if fields & {"start", "end", "all_day"}:
            if new_all_day != ev.all_day and data.start is None:
                if new_all_day:  # zeitgebunden -> ganztägig: lokale Daten übernehmen
                    start_in = ev.start.astimezone(self.tz).date()
                    end_in = (ev.end - timedelta(microseconds=1)).astimezone(self.tz).date() + timedelta(days=1)
                else:
                    raise ValidationError("Für einen zeitgebundenen Termin bitte Beginn und Ende angeben")
            else:
                start_in = data.start if data.start is not None else self._as_input(ev.start, ev.all_day)
                if data.end is not None:
                    end_in = data.end
                elif data.start is not None:  # Dauer beibehalten
                    end_in = None
                else:
                    end_in = self._as_input(ev.end, ev.all_day)
            keep = (ev.end - ev.start) if data.start is not None and data.end is None else None
            ev.start, ev.end = self._normalize_times(start_in, end_in, new_all_day, keep)
            ev.all_day = new_all_day

        if "timezone" in fields and data.timezone:
            ev.timezone = self._validate_tz(data.timezone)
        if "title" in fields and data.title:
            ev.title = data.title.strip()
        for key in ("description", "location", "category"):
            if key in fields:
                setattr(ev, key, getattr(data, key))
        if "rrule" in fields:
            ev.rrule = recurrence.validate_rrule(data.rrule, ev.start) if data.rrule else None
            if not ev.rrule:
                ev.exdates = []
        elif ev.rrule and fields & {"start", "all_day"}:
            ev.rrule = recurrence.validate_rrule(ev.rrule, ev.start)
        if "member_ids" in fields and data.member_ids is not None:
            MemberService(self.session).ensure_exist(data.member_ids)
            self._set_members(ev.id, data.member_ids)

        ev.updated_at = utcnow()
        ev.pending_push = self._is_remote(cal)
        self.session.add(ev)
        self.session.commit()
        self.session.refresh(ev)
        return ev

    def delete_event(self, event_id: int, occurrence_start: datetime | None = None) -> None:
        ev = self._get_event(event_id)
        if ev.recurrence_master_id is not None and occurrence_start is None and ev.original_start is not None:
            # Einzeländerung löschen = dieses Vorkommen der Serie absagen
            return self.delete_event(ev.recurrence_master_id, ev.original_start)
        cal = self.get_calendar(ev.calendar_id)
        self._ensure_writable(cal)

        if occurrence_start is not None:
            if not ev.rrule:
                raise ValidationError("occurrence_start ist nur bei wiederkehrenden Terminen erlaubt")
            occ = occurrence_start.astimezone(UTC)
            self._assert_is_occurrence(ev, occ)
            override = self._find_override(ev.id, occ)
            if override is not None:
                self._delete_single(override, cal)
            iso = occ.isoformat()
            if iso not in ev.exdates:
                ev.exdates = [*ev.exdates, iso]
            ev.updated_at = utcnow()
            ev.pending_push = self._is_remote(cal)
            self.session.add(ev)
            self.session.commit()
            return

        overrides = self.session.exec(select(Event).where(Event.recurrence_master_id == ev.id)).all()
        for override in overrides:
            if override.remote_id:
                override.deleted = True  # verschwindet remote mit der Serie
                override.pending_push = False
                self.session.add(override)
            else:
                self._hard_delete_events([override])
        self._delete_single(ev, cal)
        self.session.commit()

    # --- Hilfsfunktionen --------------------------------------------------------------------

    def _get_event(self, event_id: int) -> Event:
        ev = self.session.get(Event, event_id)
        if ev is None or ev.deleted:
            raise NotFoundError(f"Termin {event_id} nicht gefunden")
        return ev

    def _ensure_writable(self, cal: Calendar) -> None:
        if cal.read_only:
            raise ForbiddenError(f"Kalender „{cal.name}“ ist schreibgeschützt")

    def _is_remote(self, cal: Calendar) -> bool:
        return self._provider_of(cal) != ProviderType.LOCAL

    def _validate_tz(self, tz_name: str | None) -> str:
        if not tz_name:
            return self.settings.locale.timezone
        try:
            ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError(f"Unbekannte Zeitzone: {tz_name}") from exc
        return tz_name

    @staticmethod
    def _as_input(value: datetime, all_day: bool) -> datetime | date:
        return utc_to_date(value) if all_day else value

    def _normalize_times(
        self,
        start: datetime | date,
        end: datetime | date | None,
        all_day: bool,
        keep_duration: timedelta | None,
    ) -> tuple[datetime, datetime]:
        if all_day:
            start_d = self._to_date(start)
            if end is None:
                end_d = start_d + (keep_duration if keep_duration else timedelta(days=1))
            else:
                end_d = self._to_date(end)
            if end_d <= start_d:
                raise ValidationError("Bei ganztägigen Terminen muss das (exklusive) Enddatum nach dem Beginn liegen")
            return date_to_utc(start_d), date_to_utc(end_d)

        if not isinstance(start, datetime) or (end is not None and not isinstance(end, datetime)):
            raise ValidationError("Für zeitgebundene Termine bitte Datum und Uhrzeit angeben")
        start_dt = ensure_aware(start, self.tz).astimezone(UTC)
        end_dt = (
            ensure_aware(end, self.tz).astimezone(UTC) if end is not None
            else start_dt + (keep_duration or timedelta(hours=1))
        )
        if end_dt <= start_dt:
            raise ValidationError("Das Ende muss nach dem Beginn liegen")
        return start_dt, end_dt

    def _to_date(self, value: datetime | date) -> date:
        if isinstance(value, datetime):
            return value.astimezone(self.tz).date() if value.tzinfo else value.date()
        return value

    def _members_for(self, event_ids: list[int]) -> dict[int, list[int]]:
        result: dict[int, list[int]] = defaultdict(list)
        if not event_ids:
            return result
        rows = self.session.exec(
            select(EventMember.event_id, EventMember.member_id)
            .join(FamilyMember, FamilyMember.id == EventMember.member_id)
            .where(EventMember.event_id.in_(event_ids))
            .order_by(FamilyMember.sort_order)
        )
        for event_id, member_id in rows:
            result[event_id].append(member_id)
        return result

    def _set_members(self, event_id: int, member_ids: list[int]) -> None:
        for link in self.session.exec(select(EventMember).where(EventMember.event_id == event_id)):
            self.session.delete(link)
        self.session.flush()
        for member_id in dict.fromkeys(member_ids):  # Duplikate entfernen, Reihenfolge behalten
            self.session.add(EventMember(event_id=event_id, member_id=member_id))

    def _occurrence(self, ev: Event, cal: Calendar, start: datetime, end: datetime,
                    member_ids: list[int], read_only: bool) -> EventOccurrence:
        recurring = bool(ev.rrule)
        return EventOccurrence(
            id=ev.id,
            occurrence_id=f"{ev.id}:{recurrence.occurrence_key(start)}" if recurring else str(ev.id),
            calendar_id=ev.calendar_id, title=ev.title, description=ev.description, location=ev.location,
            start=utc_to_date(start) if ev.all_day else start,
            end=utc_to_date(end) if ev.all_day else end,
            all_day=ev.all_day, timezone=ev.timezone, rrule=ev.rrule,
            recurring=recurring or ev.recurrence_master_id is not None,
            series_id=ev.recurrence_master_id or (ev.id if recurring else None),
            member_ids=member_ids, color=cal.color, category=ev.category, read_only=read_only,
        )

    def _sort_key(self, occ: EventOccurrence):
        if occ.all_day:
            return (datetime.combine(occ.start, datetime.min.time()), 0, occ.title)
        return (occ.start.astimezone(self.tz).replace(tzinfo=None), 1, occ.title)

    def _local_dates(self, occ: EventOccurrence) -> list[date]:
        if occ.all_day:
            first, last = occ.start, occ.end - timedelta(days=1)
        else:
            first = occ.start.astimezone(self.tz).date()
            last = (occ.end - timedelta(microseconds=1)).astimezone(self.tz).date()
        out, d = [], first
        while d <= last:
            out.append(d)
            d += timedelta(days=1)
        return out

    def _assert_is_occurrence(self, master: Event, occ_start: datetime) -> None:
        spans = recurrence.expand(
            start=master.start, end=master.end, rrule=master.rrule, all_day=master.all_day,
            tz_name=master.timezone, window_start=occ_start - timedelta(seconds=1),
            window_end=occ_start + (master.end - master.start) + timedelta(seconds=1),
            display_tz=UTC if master.all_day else self.tz,
        )
        if not any(s == occ_start for s, _ in spans):
            raise NotFoundError("Dieses Vorkommen gibt es in der Serie nicht")

    def _find_override(self, master_id: int, occ_start: datetime) -> Event | None:
        return self.session.exec(
            select(Event).where(Event.recurrence_master_id == master_id, Event.original_start == occ_start)
        ).first()

    def _get_or_create_override(self, master: Event, occ_start: datetime) -> Event:
        existing = self._find_override(master.id, occ_start)
        if existing is not None:
            if existing.deleted:
                raise NotFoundError("Dieses Vorkommen wurde abgesagt")
            return existing
        self._assert_is_occurrence(master, occ_start)
        override = Event(
            calendar_id=master.calendar_id, title=master.title, description=master.description,
            location=master.location, start=occ_start, end=occ_start + (master.end - master.start),
            all_day=master.all_day, timezone=master.timezone, category=master.category,
            recurrence_master_id=master.id, original_start=occ_start,
        )
        self.session.add(override)
        self.session.flush()
        self._set_members(override.id, self._members_for([master.id]).get(master.id, []))
        return override

    def _move_event(self, ev: Event, source: Calendar, target: Calendar) -> None:
        if ev.remote_id and self._is_remote(source):
            # Grabstein im alten Kalender, damit der Sync den Remote-Termin dort löscht
            self.session.add(Event(
                calendar_id=source.id, remote_id=ev.remote_id, etag=ev.etag, title=ev.title,
                start=ev.start, end=ev.end, all_day=ev.all_day, timezone=ev.timezone,
                deleted=True, pending_push=True,
            ))
        ev.remote_id = None
        ev.etag = None
        ev.calendar_id = target.id

    def _delete_single(self, ev: Event, cal: Calendar) -> None:
        if ev.remote_id and self._is_remote(cal):
            ev.deleted = True
            ev.pending_push = True
            ev.updated_at = utcnow()
            self.session.add(ev)
        else:
            self._hard_delete_events([ev])

    def _hard_delete_events(self, events: list[Event]) -> None:
        ids = [e.id for e in events]
        if not ids:
            return
        for link in self.session.exec(select(EventMember).where(EventMember.event_id.in_(ids))):
            self.session.delete(link)
        children = self.session.exec(select(Event).where(and_(
            Event.recurrence_master_id.in_(ids), Event.id.not_in(ids)
        ))).all()
        if children:
            self._hard_delete_events(children)
        self.session.flush()
        for e in events:
            self.session.delete(e)
        self.session.flush()
