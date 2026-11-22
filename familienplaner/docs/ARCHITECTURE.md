# Familienplaner – Architektur

> Stand v0.2: Grundgerüst, Backend-Kern und Kalenderansichten sind umgesetzt (siehe Kap. 13).
> Dieses Dokument beschreibt Aufbau, Komponenten, Datenmodell, Schnittstellen und Deployment.

---

## 1. Ziele & Anforderungen

| # | Anforderung | Architektur-Antwort |
|---|-------------|---------------------|
| F1 | Kalender mit **Monats- und Wochenansicht** | Frontend-Views `MonthView`, `WeekView` |
| F2 | **Tabellarische Ansicht pro Familienmitglied** (Spalten = Personen, Zeilen = Tage/Zeitslots) | Frontend-View `FamilyTableView`, Termine werden über `Event.member_ids` zugeordnet |
| F3 | Anbindung **Google Kalender** | `GoogleCalendarProvider` (Google Calendar API v3, OAuth2 Desktop-Client mit PKCE) |
| F4 | Anbindung **Apple-/iCloud-Kalender** | `ICloudCalendarProvider` (CalDAV, app-spezifisches Passwort) |
| F5 | **Wählbare Farbschemata** | Theme-System über Design-Tokens (CSS Custom Properties) + Theme-JSON |
| F6 | **Freizeitaktivitäten im Umkreis suchen** (Tag der offenen Tür, Messen, Ausstellungen …) und in den Kalender übernehmen | `ActivityService` mit austauschbaren `ActivitySource`-Plugins, Geocoding und Umkreisfilter |
| N1 | Läuft auf **Raspberry Pi** mit 10–12"-Display | Leichtgewichtiges Backend (Python/FastAPI) + statisches Frontend in Chromium-Kiosk |
| N2 | Alternative **E-Ink-Anzeige** | Separater Render-Pfad: Server-seitiger Screenshot → Dithering → E-Ink-Treiber |
| N3 | Offline-fähig / robust | Lokaler SQLite-Cache, Sync im Hintergrund, Anzeige funktioniert ohne Internet |
| N4 | Bedienbar ohne Tastatur am Pi | Touch-optimierte UI. Einrichtung (Logins, Einstellungen) bequem per Smartphone/Laptop im Heimnetz |
| N5 | Datenschutz | Alles lokal auf dem Pi. Tokens verschlüsselt. Kein Cloud-Backend eigener Art |

---

## 2. Systemüberblick

```mermaid
flowchart LR
    subgraph Pi["Raspberry Pi (Raspberry Pi OS Bookworm)"]
        direction TB
        subgraph Display["Anzeige"]
            Kiosk["Chromium Kiosk<br/>(cage / Wayland)"]
            EInk["E-Ink Renderer<br/>(optional)"]
        end

        subgraph Backend["Backend – FastAPI (Python 3.11+)"]
            API["REST API + WebSocket"]
            Services["Services<br/>Sync · Activities · Geo · Themes · Members"]
            Scheduler["Scheduler<br/>(APScheduler)"]
            Providers["Provider-Adapter<br/>Calendar · Activities"]
        end

        DB[("SQLite<br/>familienplaner.db")]
        Static["Frontend-Build<br/>(Svelte, statisch)"]
    end

    Phone["Smartphone / Laptop<br/>(Einrichtung im LAN)"]

    Google["Google Calendar API"]
    ICloud["iCloud CalDAV"]
    Sources["Event-Quellen<br/>iCal-Feeds · APIs · Webseiten"]
    Geo["Geocoding<br/>(Nominatim / OSM)"]

    Kiosk -- HTTP/WS --> API
    Phone -- HTTP --> API
    API --> Static
    API --> Services
    Scheduler --> Services
    Services --> DB
    Services --> Providers
    EInk -- Screenshot der /eink-Route --> API
    Providers --> Google
    Providers --> ICloud
    Providers --> Sources
    Services --> Geo
```

**Grundprinzipien**

1. **Local-first:** Die Anzeige liest immer aus der lokalen DB. Externe Kalender werden im Hintergrund synchronisiert.
2. **Ports & Adapters (hexagonal):** Die Fachlogik kennt nur Schnittstellen (`CalendarProvider`, `ActivitySource`, `EInkDriver`). Google, iCloud, konkrete Event-Portale und Display-Hardware sind austauschbare Adapter.
3. **Eine UI, zwei Ausgabewege:** Dasselbe Frontend dient für das LCD (interaktiv) und für E-Ink (statischer Screenshot einer speziellen Route mit E-Ink-Theme).
4. **Konfiguration per Web:** Der Pi wird nach der Ersteinrichtung nicht mehr mit Tastatur bedient.

---

## 3. Technologie-Stack

| Schicht | Wahl | Begründung |
|---------|------|------------|
| Hardware | Raspberry Pi 4 (4 GB) oder Pi 5. Offizielles 10"/11"-Touch-Display oder HDMI-Touch-Display. Alternativ Waveshare 13.3" / Pimoroni Inky Impression 7.3" (E-Ink) | Genug Leistung für Chromium. E-Ink-Treiber für Python vorhanden |
| OS | Raspberry Pi OS Lite (Bookworm, 64 bit) | Schlank, kein Desktop nötig |
| Kiosk | `cage` (Wayland-Kiosk-Compositor) + Chromium `--kiosk` | Minimaler Overhead, automatischer Start |
| Backend | Python 3.11+, **FastAPI**, Uvicorn | Async, schnell, gute Libraries für CalDAV, Google API und E-Ink |
| Persistenz | **SQLite** + SQLModel (SQLAlchemy) + Alembic | Keine Server-DB nötig, einfache Backups |
| Hintergrundjobs | APScheduler (im Backend-Prozess) | Kein separater Broker auf dem Pi nötig |
| Kalender-Libs | Google Calendar REST und CalDAV direkt über `httpx` (async, gegen simulierte Server testbar), `icalendar`, `python-dateutil` (RRULE) | Wenige Abhängigkeiten, einheitliches async-Modell |
| Activities | `httpx`, `selectolax`/`beautifulsoup4` (Scraper), `icalendar`, `geopy` | Plugin-basiert |
| Frontend | **Svelte 5 + Vite + TypeScript**, statischer Build | Sehr kleiner Bundle-Footprint → flüssig auf dem Pi |
| Theming | CSS Custom Properties, Theme-Definitionen als JSON | Laufzeit-Umschaltung ohne Rebuild |
| E-Ink-Render | Playwright (headless Chromium) → PNG → Pillow (Dithering) → Treiber | Wiederverwendung der Web-Views |
| Deployment | systemd-Units, Install-Skript. Optional Docker Compose | Robust, startet nach Stromausfall von selbst |

---

## 4. Komponenten

### 4.1 Backend-Module

```
backend/app/
├── main.py                 App-Factory, Router-Registrierung, Lifespan (Scheduler), Fehler-Mapping
├── config.py               Settings (YAML + Umgebungsvariablen FP_*)
├── schemas.py              API-DTOs (Request/Response)
├── themes/                 Mitgelieferte Themes (*.json)
├── core/
│   ├── db.py               Engine (SQLite/WAL), Alembic-Migrationen, Startdaten
│   ├── deps.py             FastAPI-Dependencies, Admin-Schutz
│   ├── security.py         Verschlüsselung (Fernet), Admin-PIN (scrypt), Sitzungs-Tokens, Login-Sperre
│   ├── scheduler.py        Jobs: Sync, Minuten-Tick (Nachtmodus, Auto-Theme), Backup
│   ├── events.py           Interner Event-Bus → WebSocket-Push an das Frontend
│   ├── types.py            UTCDateTime-Spaltentyp
│   └── timeutil.py         Zeitzonen-Helfer
├── domain/
│   └── models.py           Entitäten (siehe Kap. 5)
├── providers/
│   ├── calendar/
│   │   ├── base.py         Port: CalendarProvider
│   │   ├── google.py       Adapter: Google Calendar API
│   │   ├── caldav.py       Adapter: CalDAV allgemein (sync-collection, multiget, iCalendar)
│   │   └── icloud.py       Adapter: iCloud (CalDAV mit iCloud-Adresse)
│   └── activities/
│       ├── base.py         Port: ActivitySource
│       ├── ical_feed.py    Adapter: generische iCal/ICS-Feeds (Museen, Schulen, Städte)
│       ├── rss_feed.py     Adapter: RSS/Atom-Veranstaltungsfeeds
│       ├── ticketmaster.py Adapter: Ticketmaster Discovery API (Beispiel für API-Quelle)
│       └── scraper.py      Adapter: konfigurierbarer HTML-Scraper (pro Website eine Regel)
├── services/
│   ├── sync_service.py     Zwei-Wege-Sync lokaler Termine ↔ externe Kalender
│   ├── calendar_service.py Abfragen für Monats-/Wochen-/Familienansicht, Termine schreiben
│   ├── recurrence.py       RRULE-Expansion (DST-sicher), Einzeländerungen/Ausnahmen
│   ├── settings_service.py Einstellungen aus der Oberfläche (Standardwerte aus config.yaml)
│   ├── display_service.py  Bildschirm an/aus, Helligkeit, Nachtmodus
│   ├── backup_service.py   Tägliche SQLite-Sicherung mit Rotation
│   ├── member_service.py   Familienmitglieder, Zuordnung Kalender → Person
│   ├── activity_service.py Suche, Deduplizierung, Übernahme in den Kalender
│   ├── geo_service.py      Geocoding, Umkreisberechnung (Haversine), Cache
│   └── theme_service.py    Theme-Verwaltung
├── api/
│   ├── calendar.py         /api/events, /api/calendars
│   ├── members.py          /api/members
│   ├── activities.py       /api/activities (Suche, Übernahme, Quellen)
│   ├── accounts.py         /api/accounts (Google-/iCloud-Verknüpfung)
│   ├── auth.py             /api/auth (Admin-PIN)
│   ├── settings.py         /api/settings, /api/themes
│   ├── display.py          /api/display (Bildschirm, Helligkeit)
│   └── system.py           /api/health, /api/info, /ws
└── display/eink/
    ├── renderer.py         Screenshot → Dithering → Treiber
    └── drivers/
        ├── base.py         Port: EInkDriver
        ├── waveshare.py    Adapter: Waveshare-Panels
        └── inky.py         Adapter: Pimoroni Inky
```

### 4.2 Frontend-Module

```
frontend/src/
├── App.svelte              Shell: Navigation (Tab-Leiste), Uhr/Datum, Theme-Provider
├── lib/
│   ├── api.ts              Typisierter REST-Client
│   ├── ws.ts               WebSocket-Client (Reconnect mit Backoff, Keepalive)
│   ├── types.ts            Gemeinsame Typen (gespiegelt aus Backend-Schemas)
│   ├── app.svelte.ts       Globaler Zustand (Svelte-Runes) + Hash-Routing
│   └── theme.ts            Anwenden der Design-Tokens als CSS-Variablen
├── views/
│   ├── MonthView.svelte
│   ├── WeekView.svelte
│   ├── FamilyTableView.svelte
│   ├── ActivitiesView.svelte   Suche im Umkreis, Ergebnisliste, „Zum Kalender hinzufügen“
│   ├── SettingsView.svelte     Konten, Mitglieder, Themes, Display, Activity-Quellen
│   └── EInkView.svelte         Statische, kontrastreiche Ansicht für E-Ink-Screenshots
├── lib/dates.ts, layout.ts, rrule.ts   Datumslogik, Überlappungs-Layout, Wiederholungsvorlagen (mit Vitest-Tests)
├── lib/editor.svelte.ts    Zustand des Termin-Dialogs
└── components/             Header, TabBar, Toolbar, EventChip, EventDialog, Modal, PinPad,
                            OnScreenKeyboard, ScreenOff, Toast, ThemePicker, settings/*
```

**Routen**

| Route | Zweck | Ziel |
|-------|-------|------|
| `/#/month` | Monatsansicht | LCD |
| `/#/week` | Wochenansicht | LCD |
| `/#/family` | Tabelle nach Familienmitgliedern | LCD |
| `/#/activities` | Freizeitaktivitäten suchen | LCD / Smartphone |
| `/#/settings` | Einstellungen (PIN-geschützt) | primär Smartphone |
| `/#/eink?layout=week` | Render-Ziel für E-Ink | Headless-Browser |

---

## 5. Datenmodell

```mermaid
erDiagram
    FamilyMember ||--o{ EventMember : "nimmt teil"
    Event ||--o{ EventMember : ""
    Account ||--o{ Calendar : "enthält"
    Calendar ||--o{ Event : "enthält"
    FamilyMember ||--o{ Calendar : "Standard-Besitzer"
    ActivitySource ||--o{ Activity : "liefert"
    Activity |o--o| Event : "übernommen als"

    FamilyMember {
        int id PK
        string name
        string color
        string avatar
        int sort_order
    }
    Account {
        int id PK
        string provider "google | icloud | local"
        string display_name
        blob credentials_encrypted
        datetime last_sync
    }
    Calendar {
        int id PK
        int account_id FK
        string remote_id
        string name
        string color
        bool read_only
        bool visible
        int default_member_id FK
        string sync_token "syncToken / CTag"
    }
    Event {
        int id PK
        int calendar_id FK
        string remote_id
        string etag
        string title
        string description
        string location
        datetime start
        datetime end
        bool all_day
        string rrule
        string timezone
        string category
        int activity_id FK
        datetime updated_at
        bool deleted
    }
    EventMember {
        int event_id FK
        int member_id FK
    }
    ActivitySource {
        int id PK
        string type "ical | rss | api | scraper"
        string name
        json config
        bool enabled
    }
    Activity {
        int id PK
        int source_id FK
        string external_id
        string title
        string category "open_day | fair | exhibition | ..."
        datetime start
        datetime end
        string venue
        string address
        float lat
        float lon
        string url
        string image_url
        string fingerprint "Dedup-Hash"
        datetime fetched_at
    }
```

Außerdem einfache Key-Value-Tabellen für `Settings` (Theme, Heimatort, Umkreis, Nachtmodus …) und einen `GeocodeCache`.

**Zuordnung Termine → Familienmitglieder** (für die Tabellenansicht):
1. Explizit über `EventMember` (in der UI gesetzt).
2. Fallback: `Calendar.default_member_id` (z. B. „Kalender *Lena Schule* gehört zu Lena“).
3. Optional: Regeln (z. B. Teilnehmer-E-Mail → Person). Später erweiterbar.

---

## 6. Schnittstellen (Ports)

### 6.1 `CalendarProvider`

```python
class CalendarProvider(Protocol):
    provider_id: str                                       # "google" | "icloud"
    async def authenticate(self, account: Account) -> None
    async def list_calendars(self) -> list[RemoteCalendar]
    async def fetch_changes(self, calendar: Calendar,
                            sync_token: str | None) -> ChangeSet   # delta sync
    async def create_event(self, calendar: Calendar, event: EventDraft) -> RemoteEvent
    async def update_event(self, calendar: Calendar, event: Event) -> RemoteEvent
    async def delete_event(self, calendar: Calendar, event: Event) -> None
```

| | Google | iCloud |
|---|---|---|
| Protokoll | REST (Calendar API v3) | CalDAV (`https://caldav.icloud.com`) |
| Auth | OAuth2 **Desktop-Client + PKCE**, Loopback-Weiterleitung `http://127.0.0.1:8000/…` (am Pi direkt; am Handy Adresse kopieren und einfügen) | Apple-ID + **app-spezifisches Passwort** |
| Delta-Sync | `syncToken` | CTag/ETag bzw. `sync-collection` (RFC 6578) |
| Push | optional Webhooks (benötigt öffentliche URL → im MVP **Polling**) | Polling |

### 6.2 `ActivitySource`

```python
class ActivitySource(Protocol):
    source_type: str
    async def search(self, query: ActivityQuery) -> list[ActivityCandidate]
    # ActivityQuery: center(lat, lon), radius_km, date_from, date_to,
    #                categories, keywords
```

Der `ActivityService` führt die Suche über alle aktiven Quellen aus und:
1. **normalisiert** die Ergebnisse,
2. **geocodiert** Adressen ohne Koordinaten (Nominatim, gecacht, max. 1 Anfrage/s),
3. **filtert** nach Umkreis (Haversine) und Zeitraum,
4. **dedupliziert** (Fingerprint aus normalisiertem Titel, Datum und Ort),
5. **kategorisiert** (Regeln/Schlüsselwörter, später optional per LLM),
6. übernimmt auf Wunsch eine Aktivität als `Event` in einen gewählten Kalender, für gewählte Mitglieder.

**Mögliche Quellen** (über Konfiguration hinzufügbar, ohne Code-Änderung bei iCal/RSS):
- iCal-/RSS-Feeds von Städten, Museen, Messegeländen, Schulen, Hochschulen (Tag der offenen Tür)
- Event-APIs mit Geo-Suche (z. B. Ticketmaster Discovery, Eventbrite nur für eigene Organisationen)
- Regionale Veranstaltungsportale per Scraper-Regel (Nutzungsbedingungen und `robots.txt` beachten)

### 6.3 `EInkDriver`

```python
class EInkDriver(Protocol):
    width: int
    height: int
    palette: list[tuple[int, int, int]]     # z. B. Schwarz/Weiß oder 7 Farben
    def display(self, image: "PIL.Image.Image") -> None
    def clear(self) -> None
    def sleep(self) -> None
```

### 6.4 REST-API (Übersicht)

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/events?start=&end=&members=&calendars=` | Alle Vorkommen im Zeitraum (Serien expandiert) |
| GET/POST | `/api/events[/{id}]` | Termin lesen/anlegen |
| PUT/DELETE | `/api/events/{id}[?occurrence_start=]` | Ändern/Löschen – ganze Serie oder ein Vorkommen |
| GET | `/api/family-table?start=&days=` | Tage × Familienmitglieder |
| GET/POST/PUT/DELETE | `/api/calendars[/{id}]` | Kalender (Sichtbarkeit, Farbe, Standard, Standard-Mitglied) |
| GET/POST/PUT/DELETE | `/api/members[/{id}]`, PUT `/api/members/order` | Familienmitglieder |
| GET/POST | `/api/auth/status·setup·login·logout·change-pin` | Admin-PIN |
| GET/PUT | `/api/accounts/google/config` | Google-OAuth-Client (Client-ID/Secret, verschlüsselt gespeichert) |
| POST | `/api/accounts/google/start` | Liefert die Google-Anmeldeadresse |
| GET | `/api/accounts/google/callback` | Weiterleitungsziel (Anmeldung am Pi) |
| POST | `/api/accounts/google/complete` | Anmeldung abschließen mit eingefügter Adresse (Anmeldung am Handy) |
| POST/DELETE | `/api/accounts/{id}/sync`, `/api/accounts/{id}` | Konto synchronisieren / trennen |
| POST | `/api/accounts/icloud` | iCloud-Konto verknüpfen |
| POST | `/api/sync` | Sync manuell auslösen |
| POST | `/api/activities/search` | Umkreissuche |
| POST | `/api/activities/{id}/add-to-calendar` | Aktivität übernehmen |
| GET/POST | `/api/activities/sources` | Quellen verwalten |
| GET | `/api/themes`, `/api/themes/active` | Themes |
| PUT | `/api/settings/theme` | Theme am Display wechseln (ohne PIN) |
| GET/PUT | `/api/settings` | Einstellungen (Ändern mit PIN) |
| GET/PUT | `/api/display`, POST `/api/display/wake` | Bildschirm an/aus, Helligkeit |
| GET | `/api/health`, `/api/info` | Systeminfo |
| POST | `/api/display/eink/refresh` | E-Ink-Neuzeichnung (Schritt 7) |
| WS | `/ws` | Push: `events.changed`, `calendars.changed`, `members.changed`, `sync.status`, `theme.changed`, `settings.changed`, `display.changed` |

**Berechtigungen:** Termine anlegen/ändern, Theme wechseln und das Display bedienen geht ohne PIN
(Familien-Touchscreen). Mitglieder, Kalender, Konten und Einstellungen erfordern die Admin-PIN.
Solange keine PIN gesetzt ist, ist der Admin-Bereich offen (Ersteinrichtung).

---

## 7. Zentrale Abläufe

### 7.1 Kalender-Synchronisation

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant Sync as SyncService
    participant P as CalendarProvider
    participant DB as SQLite
    participant UI as Frontend (WS)

    S->>Sync: alle 5 min: sync_all()
    loop je Konto/Kalender
        Sync->>P: fetch_changes(sync_token)
        P-->>Sync: ChangeSet (neu/geändert/gelöscht, neuer Token)
        Sync->>DB: Upsert / Soft-Delete, Token speichern
    end
    Sync->>DB: lokale, noch nicht übertragene Änderungen lesen (Outbox)
    Sync->>P: create/update/delete
    Sync-->>UI: events.changed
```

- **Konfliktregel (MVP):** „Last write wins“ anhand `updated`/ETag. Remote gewinnt bei Gleichstand.
- **Wiederkehrende Termine:** Gespeichert wird die RRULE. Die Expansion in Einzeltermine passiert beim Lesen für das angefragte Zeitfenster.
- **Outbox-Muster:** Lokale Änderungen landen zuerst in der DB (Flag `pending_push`). Dadurch funktioniert das Eintragen auch offline.

### 7.2 Aktivität suchen & hinzufügen

```mermaid
sequenceDiagram
    actor U as Nutzer
    participant UI as ActivitiesView
    participant A as ActivityService
    participant Src as ActivitySources
    participant G as GeoService
    participant Cal as CalendarService

    U->>UI: Umkreis 30 km, nächstes Wochenende, Kategorien
    UI->>A: POST /api/activities/search
    A->>Src: search(query) (parallel)
    Src-->>A: Kandidaten
    A->>G: geocode + Distanzfilter
    A-->>UI: deduplizierte, sortierte Liste
    U->>UI: „Zum Kalender hinzufügen“ (Kalender + Mitglieder)
    UI->>Cal: POST /api/activities/{id}/add-to-calendar
    Cal->>Cal: Event anlegen (pending_push) → Sync
```

### 7.3 E-Ink-Aktualisierung

1. Der Scheduler löst den Job aus (z. B. alle 15 min sowie nach `events.changed`, mit Debounce).
2. Playwright öffnet `http://localhost:8000/#/eink?layout=week` in der Auflösung des Panels.
3. Der Screenshot wird mit Pillow auf die Panel-Palette quantisiert (Floyd-Steinberg-Dithering).
4. Der `EInkDriver` zeichnet das Bild. Danach geht das Panel in den Ruhezustand.
5. Ist das Bild unverändert (Hash-Vergleich), wird nicht neu gezeichnet. Das schont das Panel.

---

## 8. Theme-System

- Jedes Theme ist eine JSON-Datei mit **Design-Tokens**. Mitgelieferte Themes liegen in `backend/app/themes/`.
  Eigene Themes können als JSON in `<datenverzeichnis>/themes/` abgelegt werden (gleiche `id` überschreibt).
  Pflicht-Tokens: `bg`, `surface`, `text`, `text-muted`, `accent`, `border`, `today`, `weekend`.

```json
{
  "id": "nordic",
  "name": "Nordisch",
  "mode": "light",
  "tokens": {
    "bg": "#F5F7FA", "surface": "#FFFFFF", "text": "#1F2933",
    "text-muted": "#616E7C", "accent": "#3E7CB1", "border": "#D9E2EC",
    "today": "#FFF3C4", "weekend": "#EEF2F6"
  },
  "memberPalette": ["#E4572E", "#29335C", "#F3A712", "#669BBC", "#7FB069"],
  "font": { "family": "Inter", "scale": 1.0 }
}
```

- Das Frontend setzt die Tokens als `--color-*`-Variablen auf `:root`. Komponenten verwenden **nur** Variablen.
- Mitgelieferte Themes: *Hell*, *Dunkel*, *Nordisch*, *Pastell (Kinder)*, *Hoher Kontrast*, *E-Ink S/W*, *E-Ink 7-Farben*.
- Optionaler **Auto-Wechsel**: Tag- und Nacht-Theme nach Uhrzeit oder Sonnenauf- und -untergang.
- Farben der Familienmitglieder bleiben über alle Themes gleich (pro Mitglied gespeichert). Das Theme liefert nur Vorschläge.

---

## 9. Sicherheit & Datenschutz

- Das Backend lauscht nur im Heimnetz (Bind an LAN-Interface, Firewall `ufw`). Erreichbar per mDNS als `familienplaner.local`.
- **Einstellungen und Konten** sind durch eine Admin-PIN geschützt (Session-Cookie). Die Kalenderanzeige ist ohne PIN sichtbar.
- OAuth-Tokens und das iCloud-Passwort werden mit Fernet verschlüsselt gespeichert. Der Schlüssel liegt in `/etc/familienplaner/secret.key` (Rechte 600).
- Der Google-OAuth-Client ist ein eigener Client des Nutzers (Typ **„Desktop-App“**). Scopes: `calendar.events`,
  `calendar.readonly`. Der ursprünglich geplante Device Flow („TV & Limited Input“) unterstützt keine
  Kalender-Berechtigungen. Anleitung: [GOOGLE_SETUP.md](GOOGLE_SETUP.md).
- Backups: tägliche Kopie der SQLite-DB (`sqlite3 .backup`), optional auf einen USB-Stick oder ein NAS.

---

## 10. Deployment auf dem Raspberry Pi

```
/opt/familienplaner/
├── backend/            (venv unter .venv)
├── frontend/dist/      (statischer Build, vom Backend ausgeliefert)
/etc/familienplaner/
├── config.yaml
└── secret.key
/var/lib/familienplaner/
├── familienplaner.db
└── backups/
```

**systemd-Units**

| Unit | Aufgabe |
|------|---------|
| `familienplaner-backend.service` | Uvicorn auf `0.0.0.0:8000` |
| `familienplaner-kiosk.service` | `cage -- chromium --kiosk http://localhost:8000` als Benutzer `kiosk`, Autologin auf tty1 |
| `familienplaner-eink.service` *(optional)* | Läuft statt Kiosk, wenn `display.mode = eink`. Startet den Renderer-Loop |

**Display-Management**
- Nachtmodus: Display zu konfigurierbaren Zeiten aus (`wlr-randr` / Backlight-Sysfs), Aufwecken per Touch.
- Optional ein PIR-Bewegungssensor an GPIO, der das Display einschaltet.

**Build-Strategie:** Das Frontend wird auf dem Entwicklungsrechner oder in CI gebaut, nur `dist/` wird übertragen. Auf dem Pi ist kein Node.js nötig.

---

## 11. Varianten LCD vs. E-Ink

| | LCD (10–12" Touch) | E-Ink (7,3"–13,3") |
|---|---|---|
| Interaktion | voll (Touch) | keine. Bedienung per Smartphone |
| Aktualisierung | live (WebSocket) | periodisch (15–60 min) |
| Ansichten | alle | Woche **oder** Familientabelle (konfigurierbar), ohne Animationen |
| Themes | alle | nur E-Ink-Themes (S/W, 7 Farben) |
| Stromverbrauch | ca. 5–8 W | < 1 W im Mittel. Pi Zero 2 W möglich |

---

## 12. Erweiterbarkeit (spätere Ausbaustufen)

- Weitere Kalender: Outlook/Microsoft 365 (Graph API) als zusätzlicher `CalendarProvider`
- Aufgaben/Einkaufsliste, Wetter-Widget, Müllabfuhrkalender (iCal)
- LLM-gestützte Extraktion von Veranstaltungen aus beliebigen Webseiten
- Sprachsteuerung / Home-Assistant-Integration (MQTT)

---

## 13. Umsetzungsplan

| Schritt | Status |
|---|---|
| 1. Fundament + Backend-Kern | ✅ umgesetzt |
| 2. Ansichten | ✅ umgesetzt |
| 3. Google-Sync | ✅ umgesetzt (gegen simulierten Google-Server getestet, noch nicht gegen echtes Google) |
| 4. iCloud-Sync | ✅ umgesetzt (gegen simulierten iCloud-Server getestet, noch nicht gegen echtes iCloud) |
| 5. Activities | offen (Datenmodell und Ports vorhanden) |
| 6. Deployment | teilweise (systemd-Units, Install-Skript als Gerüst) |
| 7. E-Ink | offen |

**Umgesetzt in Schritt 1:** Konfiguration, SQLite mit Alembic-Migrationen, lokaler Standardkalender,
Termine inkl. Serien (RRULE, DST-sicher), Einzeländerungen und Ausnahmen, Familientabelle, Mitglieder,
Kalenderverwaltung, Admin-PIN mit Sitzungen und Login-Sperre, verschlüsselter Schlüsselspeicher,
Event-Bus mit WebSocket, Scheduler (Nachtmodus, Auto-Theme, Backups, Sync-Rahmen), Themes (inkl. eigener),
Display-Steuerung (Hardware-Backlight oder Software-Abdunklung). Frontend: App-Shell mit Uhr,
Tab-Navigation, Theme-Umschaltung live per WebSocket und Bildschirm-aus-Overlay.

**Umgesetzt in Schritt 2:** Monatsansicht, Wochenansicht (Zeitraster mit Überlappungs-Layout,
Jetzt-Linie, Ganztagszeile), Familientabelle, Termin-Dialog (anlegen/ändern/löschen, Personen,
Wiederholung mit Enddatum, Kalenderwahl; bei Serien „nur dieser Termin“ oder „alle Termine“),
Filter nach Person, Wischgesten, Einstellungen (Mitglieder, Kalender, Startansicht, Wochenbeginn,
Nachtmodus, automatisches Theme, Helligkeit, Admin-PIN per Ziffernblock). Kiosk-Modus (`?kiosk=1`):
QWERTZ-Bildschirmtastatur, nach 5 min Inaktivität zurück zu „Heute“ und Verwaltung wieder sperren.

**Umgesetzt in Schritt 3:** Google-Anmeldung (Desktop-Client, PKCE, Loopback oder Adresse einfügen),
Client-Daten wahlweise in config.yaml oder verschlüsselt über die Oberfläche, Token-Erneuerung,
Kalenderliste (inkl. schreibgeschützter Kalender), Delta-Sync mit Paging und Voll-Sync bei 410,
Serien mit EXDATE, geänderte und abgesagte Einzelvorkommen in beide Richtungen, Personen-Zuordnung über
`extendedProperties.private`, Konfliktregel „jüngere Änderung gewinnt“, Sync 2 s nach lokalen Änderungen.
Behoben: ganztägige Serien mit Enddatum wurden nur einmal angezeigt.

**Umgesetzt in Schritt 4:** iCloud über einen eigenen asynchronen CalDAV-Client: Erkennung
(`current-user-principal` → `calendar-home-set`), Kalenderliste (Erinnerungen/VTODO ausgeblendet,
Schreibrechte aus `current-user-privilege-set`), Delta-Sync per `sync-collection` mit Rückfall auf
PROPFIND, `calendar-multiget`, Serien mit EXDATE und Einzelvorkommen (RECURRENCE-ID) als eine Ressource,
VTIMEZONE beim Schreiben, Personen-Zuordnung über `X-FAMILIENPLANER-MEMBERS`. Funktioniert auch mit
anderen CalDAV-Servern (Nextcloud …). Anleitung: [ICLOUD_SETUP.md](ICLOUD_SETUP.md).

**Ausbaustufen:**

1. **Fundament:** DB-Modelle, Migrationen, Settings, App-Shell, Theme-System
2. **Ansichten mit lokalen Daten:** Monat, Woche, Familientabelle, Termin-Dialog
3. **Google-Sync** (OAuth Desktop-Client, Delta-Sync, Outbox)
4. **iCloud-Sync** (CalDAV)
5. **Activities:** Geo-Service, iCal-/RSS-Quellen, Suche und Übernahme
6. **Deployment:** Install-Skript, Kiosk, Nachtmodus
7. **E-Ink-Pfad:** Renderer und Treiber
