"""Freizeitaktivitäten: Abruf aller Quellen, Normalisierung, Geocoding, Kategorisierung,
Deduplizierung, Umkreissuche und Übernahme in den Kalender."""
import asyncio
import hashlib
import logging
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, or_
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app.config import Settings
from app.core.events import EventBus
from app.core.security import SecretBox
from app.core.timeutil import UTC, utc_to_date, utcnow
from app.domain.models import Activity, ActivityCategory, ActivitySource, ActivitySourceType, Event
from app.providers.activities.base import ActivityCandidate, FetchWindow, GeoPoint, SourceError
from app.providers.activities.registry import SECRET_FIELDS, SOURCES
from app.schemas import (
    ActivityOut,
    ActivitySearch,
    ActivitySearchResult,
    ActivitySourceIn,
    ActivitySourceOut,
    ActivitySourceUpdate,
    AddToCalendar,
    EventCreate,
    SearchCenter,
)
from app.services.calendar_service import CalendarService
from app.services.categorize import categorize
from app.services.errors import NotFoundError, ValidationError
from app.services.geo_service import GeoService, distance_km
from app.services.settings_service import SettingsService

log = logging.getLogger(__name__)
REFRESH_DAYS = 90
MAX_GEOCODES_PER_REFRESH = 120     # Nominatim: 1/s → höchstens ~2 min pro Abruf
MAX_SEARCH_DAYS = 120
MAX_RESULTS = 300


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", " ", (text or "").lower()).strip()


def fingerprint(title: str, start: datetime, venue: str | None, tz: ZoneInfo) -> str:
    day = start.astimezone(tz).date().isoformat()
    return hashlib.sha1(f"{_norm(title)}|{day}|{_norm(venue)[:40]}".encode()).hexdigest()[:20]


@dataclass
class RefreshResult:
    source_id: int
    name: str
    count: int
    error: str | None


class ActivityService:
    def __init__(self, engine: Engine, settings: Settings, box: SecretBox, geo: GeoService, bus: EventBus,
                 http_transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.engine = engine
        self.settings = settings
        self.box = box
        self.geo = geo
        self.bus = bus
        self.http_transport = http_transport
        self.tz = ZoneInfo(settings.locale.timezone)
        self._lock = asyncio.Lock()

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.http_transport, timeout=30)

    # --- Quellen verwalten ------------------------------------------------------------------

    def _store_config(self, source_type: str, config: dict, previous: dict | None = None) -> dict:
        stored = {k: v for k, v in config.items() if not k.endswith("_enc")}
        for key in SECRET_FIELDS.get(source_type, []):
            value = stored.pop(key, None)
            if value and not str(value).startswith("••"):
                stored[f"{key}_enc"] = self.box.encrypt(str(value).encode()).decode()
            elif previous and f"{key}_enc" in previous:       # unverändert (maskiert) → behalten
                stored[f"{key}_enc"] = previous[f"{key}_enc"]
        return stored

    def _runtime_config(self, source: ActivitySource) -> dict:
        cfg = {k: v for k, v in source.config.items() if not k.endswith("_enc")}
        for key in SECRET_FIELDS.get(source.type.value, []):
            if f"{key}_enc" in source.config:
                cfg[key] = self.box.decrypt(source.config[f"{key}_enc"].encode()).decode()
        return cfg

    def source_out(self, source: ActivitySource) -> ActivitySourceOut:
        cfg = {k: v for k, v in source.config.items() if not k.endswith("_enc")}
        for key in SECRET_FIELDS.get(source.type.value, []):
            if f"{key}_enc" in source.config:
                cfg[key] = "••••••••"
        return ActivitySourceOut(id=source.id, type=source.type.value, name=source.name, config=cfg,
                                 enabled=source.enabled, last_fetch=source.last_fetch,
                                 last_error=source.last_error, last_count=source.last_count)

    @staticmethod
    def _validate(source_type: str, config: dict) -> None:
        try:
            SOURCES[source_type](config)
        except SourceError as exc:
            raise ValidationError(str(exc)) from exc
        url = config.get("url")
        if url and not re.match(r"^(https?|webcal)://", url):
            raise ValidationError("Die Adresse muss mit http://, https:// oder webcal:// beginnen")

    def list_sources(self, session: Session) -> list[ActivitySourceOut]:
        return [self.source_out(s) for s in session.exec(select(ActivitySource).order_by(ActivitySource.id))]

    def create_source(self, session: Session, data: ActivitySourceIn) -> ActivitySourceOut:
        self._validate(data.type, data.config)
        source = ActivitySource(type=ActivitySourceType(data.type), name=data.name.strip(),
                                config=self._store_config(data.type, data.config), enabled=data.enabled)
        session.add(source)
        session.commit()
        session.refresh(source)
        return self.source_out(source)

    def update_source(self, session: Session, source_id: int, data: ActivitySourceUpdate) -> ActivitySourceOut:
        source = self._get_source(session, source_id)
        if data.config is not None:
            merged = self._store_config(source.type.value, data.config, source.config)
            self._validate(source.type.value, {**data.config, **{
                k: "x" for k in SECRET_FIELDS.get(source.type.value, []) if f"{k}_enc" in merged}})
            source.config = merged
        if data.name:
            source.name = data.name.strip()
        if data.enabled is not None:
            source.enabled = data.enabled
        session.add(source)
        session.commit()
        session.refresh(source)
        return self.source_out(source)

    def delete_source(self, session: Session, source_id: int) -> None:
        source = self._get_source(session, source_id)
        linked = set(session.exec(select(Event.activity_id).where(Event.activity_id.is_not(None))))
        for act in session.exec(select(Activity).where(Activity.source_id == source_id)):
            if act.id in linked:
                # bereits in den Kalender übernommen → Termin behält seine Daten, Verknüpfung lösen
                for ev in session.exec(select(Event).where(Event.activity_id == act.id)):
                    ev.activity_id = None
                    session.add(ev)
                session.flush()
            session.delete(act)
        session.flush()
        session.delete(source)
        session.commit()

    def _get_source(self, session: Session, source_id: int) -> ActivitySource:
        source = session.get(ActivitySource, source_id)
        if source is None:
            raise NotFoundError(f"Quelle {source_id} nicht gefunden")
        return source

    def import_config_sources(self, session: Session) -> None:
        """Quellen aus der config.yaml einmalig übernehmen (Name als Schlüssel)."""
        existing = set(session.exec(select(ActivitySource.name)))
        for raw in self.settings.activities.sources:
            name, stype = raw.get("name"), raw.get("type")
            if not name or name in existing or stype not in SOURCES:
                continue
            config = {k: v for k, v in raw.items() if k not in ("name", "type", "enabled")}
            session.add(ActivitySource(type=ActivitySourceType(stype), name=name,
                                       config=self._store_config(stype, config), enabled=raw.get("enabled", True)))
        session.commit()

    # --- Abruf ------------------------------------------------------------------------------

    def _window(self, session: Session) -> FetchWindow:
        user = SettingsService(session, self.settings).get()
        center = GeoPoint(user.home.lat, user.home.lon) if user.home.lat is not None else None
        today = datetime.now(self.tz).date()
        return FetchWindow(date_from=today, date_to=today + timedelta(days=REFRESH_DAYS), center=center,
                           radius_km=max(user.activity_radius_km, 50), timezone=self.settings.locale.timezone)

    async def test_source(self, data: ActivitySourceIn) -> list[ActivityCandidate]:
        self._validate(data.type, data.config)
        with Session(self.engine) as session:
            window = self._window(session)
        async with self.http_client() as http:
            try:
                return await SOURCES[data.type](data.config).fetch(http, window)
            except SourceError as exc:
                raise ValidationError(str(exc)) from exc

    async def refresh_all(self, only_source: int | None = None) -> list[RefreshResult]:
        async with self._lock:
            results = []
            async with self.http_client() as http:
                with Session(self.engine) as session:
                    window = self._window(session)
                    query = select(ActivitySource).where(ActivitySource.enabled == True)  # noqa: E712
                    if only_source is not None:
                        query = select(ActivitySource).where(ActivitySource.id == only_source)
                    budget = [MAX_GEOCODES_PER_REFRESH]
                    for source in session.exec(query).all():
                        results.append(await self._refresh_source(session, http, source, window, budget))
                    self._purge_past(session)
            await self.bus.publish("activities.changed", {})
            return results

    async def _refresh_source(self, session: Session, http: httpx.AsyncClient, source: ActivitySource,
                              window: FetchWindow, budget: list[int]) -> RefreshResult:
        try:
            adapter = SOURCES[source.type.value](self._runtime_config(source))
            candidates = await adapter.fetch(http, window)
        except (SourceError, ValueError) as exc:
            source.last_error = str(exc)[:500]
            source.last_fetch = utcnow()
            session.add(source)
            session.commit()
            return RefreshResult(source.id, source.name, 0, source.last_error)
        except Exception as exc:  # unerwartete Formate dürfen andere Quellen nicht stoppen
            log.exception("Quelle %s fehlgeschlagen", source.name)
            source.last_error = f"Unerwarteter Fehler: {exc}"[:500]
            session.add(source)
            session.commit()
            return RefreshResult(source.id, source.name, 0, source.last_error)

        default_point = None
        cfg = source.config
        if cfg.get("lat") is not None and cfg.get("lon") is not None:
            default_point = GeoPoint(float(cfg["lat"]), float(cfg["lon"]))
        default_cat = ActivityCategory(cfg["category"]) if cfg.get("category") in ActivityCategory._value2member_map_ \
            else None

        seen: set[str] = set()
        for cand in candidates:
            fp = fingerprint(cand.title, cand.start, cand.venue or cand.address, self.tz)
            if fp in seen:
                continue
            seen.add(fp)
            point = cand.location
            if point is None and cand.address and budget[0] > 0:
                budget[0] -= 1
                try:
                    point = await self.geo.geocode(session, http, cand.address)
                except httpx.HTTPError as exc:
                    log.warning("Geocoding nicht erreichbar: %s", exc)
                    budget[0] = 0
            point = point or default_point
            existing = session.exec(select(Activity).where(Activity.fingerprint == fp)).first()
            if existing and existing.source_id != source.id:
                if existing.lat is None and point:           # Duplikat aus anderer Quelle: Ort ergänzen
                    existing.lat, existing.lon = point.lat, point.lon
                    session.add(existing)
                continue
            act = existing or Activity(source_id=source.id, title=cand.title, start=cand.start, fingerprint=fp)
            act.external_id = cand.external_id
            act.title = cand.title[:300]
            act.description = (cand.description or "")[:4000] or None
            act.category = categorize(cand.title, cand.description, cand.category_hints, default_cat)
            act.start, act.end, act.all_day = cand.start, cand.end, cand.all_day
            act.venue, act.address = cand.venue, cand.address
            act.lat, act.lon = (point.lat, point.lon) if point else (None, None)
            act.url, act.image_url = cand.url, cand.image_url
            act.fetched_at = utcnow()
            session.add(act)

        # Nicht mehr gelieferte zukünftige Termine dieser Quelle entfernen
        linked = set(session.exec(select(Event.activity_id).where(Event.activity_id.is_not(None))))
        start_today = datetime.combine(window.date_from, time.min, tzinfo=self.tz).astimezone(UTC)
        for act in session.exec(select(Activity).where(Activity.source_id == source.id,
                                                       Activity.start >= start_today)):
            if act.fingerprint not in seen and act.id not in linked:
                session.delete(act)
        source.last_fetch = utcnow()
        source.last_error = None
        source.last_count = len(seen)
        session.add(source)
        session.commit()
        return RefreshResult(source.id, source.name, len(seen), None)

    def _purge_past(self, session: Session) -> None:
        cutoff = utcnow() - timedelta(days=2)
        linked = set(session.exec(select(Event.activity_id).where(Event.activity_id.is_not(None))))
        for act in session.exec(select(Activity).where(func.coalesce(Activity.end, Activity.start) < cutoff)):
            if act.id not in linked:
                session.delete(act)
        session.commit()

    # --- Suche ------------------------------------------------------------------------------

    async def resolve_center(self, session: Session, req: ActivitySearch) -> SearchCenter:
        if req.lat is not None and req.lon is not None:
            return SearchCenter(lat=req.lat, lon=req.lon, label=req.address or "Gewählter Ort")
        if req.address and req.address.strip():
            async with self.http_client() as http:
                point = await self.geo.geocode(session, http, req.address)
            if point is None:
                raise ValidationError(f"Ort „{req.address}“ nicht gefunden")
            return SearchCenter(lat=point.lat, lon=point.lon, label=req.address.strip())
        home = SettingsService(session, self.settings).get().home
        if home.lat is None or home.lon is None:
            raise ValidationError("Bitte zuerst den Wohnort in den Einstellungen festlegen oder einen Ort angeben")
        return SearchCenter(lat=home.lat, lon=home.lon, label=home.address or "Wohnort")

    async def search(self, session: Session, req: ActivitySearch) -> ActivitySearchResult:
        if req.date_to < req.date_from:
            raise ValidationError("Das Enddatum muss nach dem Startdatum liegen")
        if (req.date_to - req.date_from).days > MAX_SEARCH_DAYS:
            raise ValidationError(f"Zeitraum höchstens {MAX_SEARCH_DAYS} Tage")
        center = await self.resolve_center(session, req)
        lo = datetime.combine(req.date_from, time.min, tzinfo=self.tz).astimezone(UTC)
        hi = datetime.combine(req.date_to + timedelta(days=1), time.min, tzinfo=self.tz).astimezone(UTC)

        stmt = select(Activity, ActivitySource.name).join(ActivitySource).where(
            Activity.start < hi + timedelta(days=1),       # Puffer für ganztägige Termine (Datumssemantik)
            func.coalesce(Activity.end, Activity.start) > lo - timedelta(days=1),
            ActivitySource.enabled == True,  # noqa: E712
        )
        if req.categories:
            valid = [c for c in req.categories if c in ActivityCategory._value2member_map_]
            stmt = stmt.where(Activity.category.in_([ActivityCategory(c) for c in valid]))
        if req.query and req.query.strip():
            like = f"%{req.query.strip()}%"
            stmt = stmt.where(or_(Activity.title.ilike(like), Activity.description.ilike(like),
                                  Activity.venue.ilike(like)))
        dlat = req.radius_km / 111.0
        dlon = req.radius_km / max(1e-6, 111.0 * abs(math.cos(math.radians(center.lat))))
        box = (Activity.lat.between(center.lat - dlat, center.lat + dlat)
               & Activity.lon.between(center.lon - dlon, center.lon + dlon))
        stmt = stmt.where(or_(box, Activity.lat.is_(None)) if req.include_unlocated else box)

        added = dict(session.exec(select(Event.activity_id, Event.id).where(
            Event.activity_id.is_not(None), Event.deleted == False)).all())  # noqa: E712
        origin = GeoPoint(center.lat, center.lon)
        results: list[ActivityOut] = []
        for act, source_name in session.exec(stmt).all():
            if not self._in_window(act, req.date_from, req.date_to):
                continue
            dist = None
            if act.lat is not None:
                dist = round(distance_km(origin, GeoPoint(act.lat, act.lon)), 1)
                if dist > req.radius_km:
                    continue
            results.append(self._out(act, source_name, dist, added.get(act.id)))
        results.sort(key=lambda r: (self._sort_start(r), r.distance_km if r.distance_km is not None else 1e9))
        total = session.exec(select(func.count(Activity.id))).one()
        return ActivitySearchResult(center=center, results=results[:MAX_RESULTS], total_in_db=total)

    def _in_window(self, act: Activity, d_from: date, d_to: date) -> bool:
        if act.all_day:
            first = utc_to_date(act.start)
            last = utc_to_date(act.end) - timedelta(days=1) if act.end else first
        else:
            first = act.start.astimezone(self.tz).date()
            last = (act.end - timedelta(microseconds=1)).astimezone(self.tz).date() if act.end else first
        return first <= d_to and last >= d_from

    def _sort_start(self, r: ActivityOut) -> datetime:
        if isinstance(r.start, datetime):
            return r.start.astimezone(self.tz).replace(tzinfo=None)
        return datetime.combine(r.start, time.min)

    @staticmethod
    def _out(act: Activity, source: str, dist: float | None, event_id: int | None) -> ActivityOut:
        return ActivityOut(
            id=act.id, title=act.title, description=act.description, category=act.category.value,
            start=utc_to_date(act.start) if act.all_day else act.start,
            end=(utc_to_date(act.end) if act.all_day else act.end) if act.end else None,
            all_day=act.all_day, venue=act.venue, address=act.address, lat=act.lat, lon=act.lon,
            distance_km=dist, url=act.url, image_url=act.image_url, source=source, event_id=event_id,
        )

    # --- Übernahme in den Kalender ----------------------------------------------------------

    def add_to_calendar(self, session: Session, activity_id: int, data: AddToCalendar) -> Event:
        act = session.get(Activity, activity_id)
        if act is None:
            raise NotFoundError("Aktivität nicht gefunden (evtl. inzwischen abgelaufen)")
        location = ", ".join(dict.fromkeys(x for x in (act.venue, act.address) if x)) or None
        description = "\n\n".join(x for x in (act.description, act.url) if x) or None
        if act.all_day:
            start, end = utc_to_date(act.start), utc_to_date(act.end) if act.end else None
        else:
            start = act.start
            end = act.end if act.end and act.end > act.start else act.start + timedelta(hours=2)
        svc = CalendarService(session, self.settings)
        ev = svc.create_event(EventCreate(
            calendar_id=data.calendar_id, title=act.title[:300], start=start, end=end, all_day=act.all_day,
            location=location[:500] if location else None, description=description,
            member_ids=data.member_ids, category=act.category.value,
        ))
        ev.activity_id = act.id
        session.add(ev)
        session.commit()
        session.refresh(ev)
        return ev
