# Familienplaner

Familienkalender für Raspberry Pi mit Touch-Display (10–12") oder E-Ink-Anzeige.

- Monats- und Wochenansicht sowie eine Tabellenansicht pro Familienmitglied
- Synchronisation mit **Google Kalender** und **Apple/iCloud-Kalender**
- Wählbare Farbschemata (Themes)
- Suche nach Freizeitaktivitäten im Umkreis (Tag der offenen Tür, Messen, Ausstellungen …) mit Übernahme in den Kalender

> **Status:** Architektur und Code-Gerüst. Die Funktionen sind noch nicht implementiert.
> Siehe [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Struktur

| Ordner | Inhalt |
|--------|--------|
| `backend/` | FastAPI-Backend (Python): API, Services, Provider-Adapter, E-Ink-Renderer |
| `frontend/` | Svelte + Vite + TypeScript: Kalender-UI, Themes |
| `config/` | Beispielkonfiguration |
| `deploy/` | systemd-Units, Kiosk-Setup, Install-Skript für den Raspberry Pi |
| `docs/` | Architektur |
