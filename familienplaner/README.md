# Familienplaner

Familienkalender für Raspberry Pi mit Touch-Display (10–12") oder E-Ink-Anzeige.

- Monats- und Wochenansicht sowie eine Tabellenansicht pro Familienmitglied
- Synchronisation mit **Google Kalender** und **Apple/iCloud-Kalender**
- Wählbare Farbschemata (Themes)
- Suche nach Freizeitaktivitäten im Umkreis (Tag der offenen Tür, Messen, Ausstellungen …) mit Übernahme in den Kalender

> **Status:** Grundgerüst, Backend, Kalenderansichten und Google-Sync sind umgesetzt. iCloud-Sync,
> Aktivitätensuche und E-Ink folgen. Siehe [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), Kap. 13.

## Struktur

| Ordner | Inhalt |
|--------|--------|
| `backend/` | FastAPI-Backend (Python): API, Services, Provider-Adapter, Migrationen, Tests |
| `frontend/` | Svelte 5 + Vite + TypeScript: App-Shell, Ansichten |
| `config/` | Beispielkonfiguration |
| `deploy/` | systemd-Units, Kiosk-Setup, Install-Skript für den Raspberry Pi |
| `docs/` | Architektur, [Google-Einrichtung](docs/GOOGLE_SETUP.md) |

## Entwicklung

Voraussetzungen: Python ≥ 3.11, Node.js ≥ 20.

```bash
# Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                                   # Tests
uvicorn --factory app.main:app_factory --reload --port 8000
# → API-Doku: http://localhost:8000/docs   (Daten liegen in backend/data/)

# Frontend (zweites Terminal)
cd frontend
npm install
npm run dev                              # http://localhost:5173, leitet /api und /ws an :8000 weiter
npm test                                 # Unit-Tests (Vitest)
npm run build                            # Build nach frontend/dist – wird vom Backend unter / ausgeliefert
# Kiosk-Modus (Bildschirmtastatur usw.) testen: http://localhost:5173/?kiosk=1
```

Konfiguration: `config/config.example.yaml` nach `/etc/familienplaner/config.yaml` kopieren oder mit
`FP_CONFIG_FILE=<pfad>` angeben. Einzelwerte lassen sich per Umgebungsvariable überschreiben,
z. B. `FP_DISPLAY__THEME=dark` oder `FP_LOCALE__TIMEZONE=Europe/Vienna`.

Datenbank-Migration nach Modelländerungen:

```bash
cd backend
alembic -x db=data/familienplaner.db revision --autogenerate -m "beschreibung"
```

Beim Start werden Migrationen automatisch angewendet.
