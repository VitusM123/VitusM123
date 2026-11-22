"""Google-Sync gegen einen simulierten Google-Server."""
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import GoogleSettings
from app.domain.models import Account, Event
from app.main import create_app
from tests.fake_google import FakeGoogle

PRIMARY = "family@gmail.com"
HOLIDAYS = "de.german#holiday@group.v.calendar.google.com"


@pytest.fixture
def fake():
    g = FakeGoogle()
    g.add_calendar(PRIMARY, "Familie (Google)", primary=True)
    g.add_calendar(HOLIDAYS, "Feiertage", role="reader", color="#16a765")
    t = lambda h, m=0: f"T{h:02d}:{m:02d}:00+01:00"  # noqa: E731
    g.put_event(PRIMARY, {"id": "e1", "summary": "Arzt", "start": {"dateTime": "2026-11-24" + t(10)},
                          "end": {"dateTime": "2026-11-24" + t(11)}})
    g.put_event(PRIMARY, {"id": "e2", "summary": "Ausflug", "start": {"date": "2026-11-28"},
                          "end": {"date": "2026-11-29"}})
    g.put_event(PRIMARY, {"id": "r1", "summary": "Turnen",
                          "start": {"dateTime": "2026-11-02" + t(16), "timeZone": "Europe/Berlin"},
                          "end": {"dateTime": "2026-11-02" + t(17), "timeZone": "Europe/Berlin"},
                          "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=MO", "EXDATE;TZID=Europe/Berlin:20261109T160000"]})
    g.put_event(PRIMARY, {"id": "r1_20261116T150000Z", "recurringEventId": "r1", "summary": "Turnen (Halle 2)",
                          "originalStartTime": {"dateTime": "2026-11-16" + t(16)},
                          "start": {"dateTime": "2026-11-16" + t(17)}, "end": {"dateTime": "2026-11-16" + t(18)}})
    g.put_event(PRIMARY, {"id": "r1_20261123T150000Z", "status": "cancelled", "recurringEventId": "r1",
                          "originalStartTime": {"dateTime": "2026-11-23" + t(16)}})
    g.put_event(PRIMARY, {"id": "e3", "summary": "Kino", "start": {"dateTime": "2026-11-27" + t(20)},
                          "end": {"dateTime": "2026-11-27" + t(22)},
                          "extendedProperties": {"private": {"familienplaner_members": "1"}}})
    g.put_event(HOLIDAYS, {"id": "h1", "summary": "1. Advent", "start": {"date": "2026-11-29"},
                           "end": {"date": "2026-11-30"}})
    return g


@pytest.fixture
def gclient(settings, fake):
    settings.google = GoogleSettings(client_id="123-abc.apps.googleusercontent.com", client_secret="secret-123456")
    app = create_app(settings, start_scheduler=False, http_transport=fake.transport)
    app.state.sync.auto_sync = False
    with TestClient(app) as c:
        c.post("/api/members", json={"name": "Anna", "color": "#E4572E"})
        c.post("/api/members", json={"name": "Ben", "color": "#29335C"})
        yield c


def connect(client, fake) -> dict:
    r = client.post("/api/accounts/google/start")
    assert r.status_code == 200, r.text
    q = parse_qs(urlparse(r.json()["auth_url"]).query)
    assert q["redirect_uri"] == ["http://127.0.0.1:8000/api/accounts/google/callback"]
    assert q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"]
    assert "calendar.events" in q["scope"][0]
    fake.authorize("code-abc", q["code_challenge"][0])
    pasted = f"http://127.0.0.1:8000/api/accounts/google/callback?state={q['state'][0]}&code=code-abc&scope=x"
    r = client.post("/api/accounts/google/complete", json={"url": pasted})
    assert r.status_code == 200, r.text
    assert client.post("/api/sync").json()["state"] == "idle"
    return r.json()


def events(client, start="2026-11-01T00:00:00", end="2026-12-15T00:00:00"):
    return client.get("/api/events", params={"start": start, "end": end}).json()


def titles(client, **kw):
    return [(e["title"], e["start"]) for e in events(client, **kw)]


def cal_id(client, remote_name):
    return next(c["id"] for c in client.get("/api/calendars").json() if c["name"] == remote_name)


def test_connect_and_initial_import(gclient, fake):
    account = connect(gclient, fake)
    assert account["display_name"] == PRIMARY and account["provider"] == "google"
    cals = {c["name"]: c for c in gclient.get("/api/calendars").json()}
    assert cals["Feiertage"]["read_only"] and not cals["Familie (Google)"]["read_only"]
    # Hauptkalender des neuen Kontos ist jetzt Standard für neue Termine
    assert cals["Familie (Google)"]["is_default"] and not cals["Familie"]["is_default"]
    ev = gclient.post("/api/events", json={"title": "Neu", "start": "2026-11-30T10:00:00"}).json()
    assert ev["calendar_id"] == cals["Familie (Google)"]["id"]

    evs = events(gclient)
    turnen = [(e["title"], e["start"]) for e in evs if e["title"].startswith("Turnen")]
    assert turnen == [
        ("Turnen", "2026-11-02T15:00:00Z"),            # 9.11. per EXDATE ausgenommen
        ("Turnen (Halle 2)", "2026-11-16T16:00:00Z"),  # geändertes Vorkommen
        ("Turnen", "2026-11-30T15:00:00Z"),            # 23.11. abgesagt
        ("Turnen", "2026-12-07T15:00:00Z"),
        ("Turnen", "2026-12-14T15:00:00Z"),
    ]
    by_title = {e["title"]: e for e in evs}
    assert by_title["Ausflug"]["all_day"] and by_title["Ausflug"]["start"] == "2026-11-28"
    assert by_title["Kino"]["member_ids"] == [1]
    assert by_title["1. Advent"]["read_only"] is True

    # Schreibgeschützter Kalender: lokales Anlegen verboten
    r = gclient.post("/api/events", json={"title": "X", "start": "2026-11-24T10:00:00",
                                          "calendar_id": cals["Feiertage"]["id"]})
    assert r.status_code == 403


def test_credentials_are_encrypted(gclient, fake):
    connect(gclient, fake)
    with Session(gclient.app.state.engine) as s:
        acc = s.exec(select(Account).where(Account.display_name == PRIMARY)).one()
        assert b"refresh-1" not in acc.credentials_encrypted
        assert acc.last_sync is not None


def test_incremental_changes(gclient, fake):
    connect(gclient, fake)
    item = dict(fake.events[PRIMARY]["e1"])
    item["summary"] = "Arzt (verschoben)"
    fake.put_event(PRIMARY, item)
    fake.remove_event(PRIMARY, "e2")
    before = len(fake.requests)
    gclient.post("/api/sync")
    listed = [p for m, p in fake.requests[before:] if m == "GET" and p.endswith("/events")]
    assert listed, "Delta-Abruf erwartet"
    names = [t for t, _ in titles(gclient)]
    assert "Arzt (verschoben)" in names and "Ausflug" not in names


def test_push_local_changes(gclient, fake):
    connect(gclient, fake)
    cid = cal_id(gclient, "Familie (Google)")
    # Neu anlegen mit Person
    ev = gclient.post("/api/events", json={"title": "Elternabend", "start": "2026-11-26T19:00:00",
                                           "end": "2026-11-26T20:30:00", "calendar_id": cid,
                                           "member_ids": [2]}).json()
    gclient.post("/api/sync")
    remote = [e for e in fake.events[PRIMARY].values() if e.get("summary") == "Elternabend"]
    assert len(remote) == 1
    assert remote[0]["start"] == {"dateTime": "2026-11-26T19:00:00+01:00", "timeZone": "Europe/Berlin"}
    assert remote[0]["extendedProperties"]["private"]["familienplaner_members"] == "2"
    rid = remote[0]["id"]

    # Ändern
    gclient.put(f"/api/events/{ev['id']}", json={"title": "Elternabend 3b"})
    gclient.post("/api/sync")
    assert fake.events[PRIMARY][rid]["summary"] == "Elternabend 3b"
    # Lokale Zuordnung bleibt nach dem Rückweg erhalten
    assert gclient.get(f"/api/events/{ev['id']}").json()["member_ids"] == [2]

    # Löschen
    gclient.delete(f"/api/events/{ev['id']}")
    gclient.post("/api/sync")
    assert fake.events[PRIMARY][rid]["status"] == "cancelled"
    with Session(gclient.app.state.engine) as s:
        assert s.exec(select(Event).where(Event.remote_id == rid)).first() is None


def test_push_series_exception_and_override(gclient, fake):
    connect(gclient, fake)
    master_id = next(e["id"] for e in events(gclient) if e["title"] == "Turnen")
    # Vorkommen am 30.11. absagen → EXDATE an der Serie
    gclient.delete(f"/api/events/{master_id}", params={"occurrence_start": "2026-11-30T15:00:00Z"})
    # Vorkommen am 7.12. verschieben → Instanz wird geschrieben
    r = gclient.put(f"/api/events/{master_id}", params={"occurrence_start": "2026-12-07T15:00:00Z"},
                    json={"start": "2026-12-07T18:00:00", "title": "Turnen (spät)"})
    assert r.status_code == 200, r.text
    gclient.post("/api/sync")
    recurrence = fake.events[PRIMARY]["r1"]["recurrence"]
    assert "EXDATE;TZID=Europe/Berlin:20261130T160000" in recurrence
    assert "EXDATE;TZID=Europe/Berlin:20261109T160000" in recurrence
    inst = fake.events[PRIMARY]["r1_20261207T150000Z"]
    assert inst["summary"] == "Turnen (spät)" and inst["recurringEventId"] == "r1"
    assert inst["start"]["dateTime"] == "2026-12-07T18:00:00+01:00"
    # Zweiter Sync: nichts wiederholt sich, Ansicht stabil
    gclient.post("/api/sync")
    turnen = [(t, s) for t, s in titles(gclient) if t.startswith("Turnen")]
    assert ("Turnen", "2026-11-30T15:00:00Z") not in turnen
    assert ("Turnen (spät)", "2026-12-07T17:00:00Z") in turnen
    assert len([t for t in turnen if t[0] == "Turnen (spät)"]) == 1


def test_sync_token_expired_triggers_full_resync(gclient, fake):
    connect(gclient, fake)
    fake.expired_sync_tokens = True
    del fake.events[PRIMARY]["e1"]          # verschwindet ohne Lösch-Eintrag
    assert gclient.post("/api/sync").json()["state"] == "idle"
    assert "Arzt" not in [t for t, _ in titles(gclient)]
    assert "Kino" in [t for t, _ in titles(gclient)]


def test_token_refresh_and_revocation(gclient, fake):
    connect(gclient, fake)
    fake.access_tokens.clear()               # Access-Token abgelaufen → Refresh
    assert gclient.post("/api/sync").json()["state"] == "idle"
    fake.access_tokens.clear()
    fake.refresh_tokens.clear()              # Zugriff widerrufen
    status = gclient.post("/api/sync").json()
    assert status["state"] == "error" and "neu verbinden" in status["last_error"]
    acc = next(a for a in gclient.get("/api/accounts").json() if a["provider"] == "google")
    assert "neu verbinden" in acc["last_error"]
    # Lokale Daten bleiben erhalten
    assert "Kino" in [t for t, _ in titles(gclient)]


def test_conflict_newer_wins(gclient, fake):
    connect(gclient, fake)
    kino = next(e for e in events(gclient) if e["title"] == "Kino")
    # Lokal zuerst, dann remote → remote ist jünger und gewinnt
    gclient.put(f"/api/events/{kino['id']}", json={"title": "Kino lokal"})
    item = dict(fake.events[PRIMARY]["e3"])
    item["summary"] = "Kino remote"
    fake.put_event(PRIMARY, item)
    gclient.post("/api/sync")
    assert gclient.get(f"/api/events/{kino['id']}").json()["title"] == "Kino remote"
    # Remote zuerst, dann lokal → lokal ist jünger und wird hochgeladen
    item = dict(fake.events[PRIMARY]["e3"])
    item["summary"] = "Kino remote 2"
    fake.put_event(PRIMARY, item)
    gclient.put(f"/api/events/{kino['id']}", json={"title": "Kino lokal 2"})
    gclient.post("/api/sync")
    assert gclient.get(f"/api/events/{kino['id']}").json()["title"] == "Kino lokal 2"
    assert fake.events[PRIMARY]["e3"]["summary"] == "Kino lokal 2"


def test_callback_redirect_and_errors(gclient, fake):
    r = gclient.post("/api/accounts/google/start")
    q = parse_qs(urlparse(r.json()["auth_url"]).query)
    fake.authorize("code-xyz", q["code_challenge"][0])
    r = gclient.get("/api/accounts/google/callback", params={"state": q["state"][0], "code": "code-xyz"},
                    follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].startswith("/?google=connected&account=")
    # Erneut mit demselben state → abgelaufen/unbekannt
    r = gclient.get("/api/accounts/google/callback", params={"state": q["state"][0], "code": "code-xyz"},
                    follow_redirects=False)
    assert "google_error" in r.headers["location"]
    # Abgelehnt
    r = gclient.get("/api/accounts/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert "access_denied" in r.headers["location"]


def test_google_config_in_settings(client):
    r = client.get("/api/accounts/google/config").json()
    assert r["configured"] is False
    assert client.post("/api/accounts/google/start").status_code == 409
    assert client.put("/api/accounts/google/config",
                      json={"client_id": "nope", "client_secret": "x" * 20}).status_code == 422
    r = client.put("/api/accounts/google/config",
                   json={"client_id": "1-a.apps.googleusercontent.com", "client_secret": "GOCSPX-1234567890"})
    assert r.status_code == 200 and r.json()["source"] == "settings"
    assert client.post("/api/accounts/google/start").status_code == 200


def test_disconnect_keeps_remote(gclient, fake):
    account = connect(gclient, fake)
    assert gclient.delete(f"/api/accounts/{account['id']}").status_code == 204
    cals = gclient.get("/api/calendars").json()
    assert [c["provider"] for c in cals] == ["local"]
    assert cals[0]["is_default"]                  # Standard fällt auf den lokalen Kalender zurück
    assert gclient.post("/api/events", json={"title": "X", "start": "2026-11-30T10:00:00"}).status_code == 201
    assert "e1" in fake.events[PRIMARY]
