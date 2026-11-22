"""iCloud-Sync (CalDAV) gegen einen simulierten iCloud-Server."""
import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar as ICal
from sqlmodel import Session

from app.domain.models import Event
from app.main import create_app
from tests.fake_caldav import FakeCalDAV, ics, vevent

TZ = "TZID=Europe/Berlin"
CHOR = ics(
    vevent("r1@icloud", "Chor", f"DTSTART;{TZ}:20261104T190000", f"DTEND;{TZ}:20261104T203000",
           "RRULE:FREQ=WEEKLY;BYDAY=WE", f"EXDATE;{TZ}:20261111T190000"),
    vevent("r1@icloud", "Chor (Generalprobe)", f"DTSTART;{TZ}:20261118T180000", f"DTEND;{TZ}:20261118T210000",
           f"RECURRENCE-ID;{TZ}:20261118T190000"),
)


@pytest.fixture
def fake():
    f = FakeCalDAV()
    f.put("home", "s1.ics", ics(vevent("s1@icloud", "Elternsprechtag", f"DTSTART;{TZ}:20261124T170000",
                                       f"DTEND;{TZ}:20261124T180000", "X-FAMILIENPLANER-MEMBERS:2")))
    f.put("home", "a1.ics", ics(vevent("a1@icloud", "Flohmarkt", "DTSTART;VALUE=DATE:20261128",
                                       "DTEND;VALUE=DATE:20261129")))
    f.put("home", "r1.ics", CHOR)
    f.put("work", "w1.ics", ics(vevent("w1@icloud", "Teamtag", "DTSTART:20261126T080000Z", "DTEND:20261126T160000Z")))
    return f


@pytest.fixture
def iclient(settings, fake):
    app = create_app(settings, start_scheduler=False, http_transport=fake.transport)
    app.state.sync.auto_sync = False
    with TestClient(app) as c:
        c.post("/api/members", json={"name": "Anna", "color": "#E4572E"})
        c.post("/api/members", json={"name": "Ben", "color": "#29335C"})
        yield c


def connect(client):
    r = client.post("/api/accounts/icloud", json={"apple_id": "anna@icloud.com",
                                                  "app_password": "abcd-efgh-ijkl-mnop"})
    assert r.status_code == 200, r.text
    assert client.post("/api/sync").json()["state"] == "idle"
    return r.json()


def events(client, start="2026-11-01T00:00:00", end="2026-12-10T00:00:00"):
    return client.get("/api/events", params={"start": start, "end": end}).json()


def home_id(client):
    return next(c["id"] for c in client.get("/api/calendars").json() if c["name"] == "Zuhause")


def test_connect_validation(iclient):
    r = iclient.post("/api/accounts/icloud", json={"apple_id": "anna@icloud.com", "app_password": "MeinPasswort1"})
    assert r.status_code == 422 and "app-spezifisches" in r.json()["detail"]
    r = iclient.post("/api/accounts/icloud", json={"apple_id": "anna@icloud.com",
                                                   "app_password": "zzzz-zzzz-zzzz-zzzz"})
    assert r.status_code == 422 and "ungültig" in r.json()["detail"]


def test_connect_and_import(iclient, fake):
    acc = connect(iclient)
    assert acc["provider"] == "icloud" and acc["display_name"] == "anna@icloud.com"
    cals = {c["name"]: c for c in iclient.get("/api/calendars").json() if c["provider"] == "icloud"}
    assert set(cals) == {"Zuhause", "Arbeit (geteilt)"}          # Erinnerungen (VTODO) ausgelassen
    assert cals["Arbeit (geteilt)"]["read_only"] and cals["Zuhause"]["color"] == "#FF2968"
    assert cals["Zuhause"]["is_default"]          # neue Termine landen in iCloud

    evs = events(iclient)
    chor = [(e["title"], e["start"]) for e in evs if e["title"].startswith("Chor")]
    assert chor == [
        ("Chor", "2026-11-04T18:00:00Z"),
        ("Chor (Generalprobe)", "2026-11-18T17:00:00Z"),
        ("Chor", "2026-11-25T18:00:00Z"),
        ("Chor", "2026-12-02T18:00:00Z"),
        ("Chor", "2026-12-09T18:00:00Z"),
    ]
    by = {e["title"]: e for e in evs}
    assert by["Elternsprechtag"]["member_ids"] == [2]
    assert by["Flohmarkt"]["all_day"] and by["Flohmarkt"]["start"] == "2026-11-28"
    assert by["Teamtag"]["read_only"]


def test_incremental_changes_and_pruned_override(iclient, fake):
    connect(iclient)
    # Generalprobe in iCloud entfernt (Serie ohne Einzeländerung), Flohmarkt gelöscht
    fake.put("home", "r1.ics", ics(vevent("r1@icloud", "Chor", f"DTSTART;{TZ}:20261104T190000",
                                          f"DTEND;{TZ}:20261104T203000", "RRULE:FREQ=WEEKLY;BYDAY=WE")))
    fake.delete("home", "a1.ics")
    iclient.post("/api/sync")
    titles = [(e["title"], e["start"]) for e in events(iclient)]
    assert ("Chor", "2026-11-18T18:00:00Z") in titles and ("Chor", "2026-11-11T18:00:00Z") in titles
    assert not any(t == "Chor (Generalprobe)" for t, _ in titles)
    assert not any(t == "Flohmarkt" for t, _ in titles)


def test_push_create_update_delete(iclient, fake):
    connect(iclient)
    ev = iclient.post("/api/events", json={"title": "Zahnarzt & Kontrolle", "start": "2026-11-27T09:00:00",
                                           "end": "2026-11-27T09:30:00", "calendar_id": home_id(iclient),
                                           "member_ids": [1]}).json()
    iclient.post("/api/sync")
    with Session(iclient.app.state.engine) as s:
        local = s.get(Event, ev["id"])
        href, uid = local.remote_id, local.remote_uid
    name = href.rsplit("/", 1)[-1]
    assert href.startswith("https://p42-caldav.icloud.com:443/1234/calendars/home/") and name == f"{uid}.ics"
    cal = ICal.from_ical(fake.data("home", name))
    vev = cal.walk("VEVENT")[0]
    assert str(vev["SUMMARY"]) == "Zahnarzt & Kontrolle" and str(vev["X-FAMILIENPLANER-MEMBERS"]) == "1"
    assert vev["DTSTART"].params["TZID"] == "Europe/Berlin" and cal.walk("VTIMEZONE")

    iclient.put(f"/api/events/{ev['id']}", json={"location": "Praxis Dr. Weber"})
    iclient.post("/api/sync")
    vev = ICal.from_ical(fake.data("home", name)).walk("VEVENT")[0]
    assert str(vev["LOCATION"]) == "Praxis Dr. Weber" and str(vev["UID"]) == uid
    assert len([e for e in events(iclient) if e["title"] == "Zahnarzt & Kontrolle"]) == 1   # keine Dublette

    iclient.delete(f"/api/events/{ev['id']}")
    iclient.post("/api/sync")
    assert name not in fake.res["home"]


def test_push_series_as_single_resource(iclient, fake):
    connect(iclient)
    master = next(e for e in events(iclient) if e["title"] == "Chor")
    # 25.11. absagen, 2.12. verschieben
    iclient.delete(f"/api/events/{master['id']}", params={"occurrence_start": "2026-11-25T18:00:00Z"})
    r = iclient.put(f"/api/events/{master['id']}", params={"occurrence_start": "2026-12-02T18:00:00Z"},
                    json={"start": "2026-12-02T20:00:00", "title": "Chor (später)"})
    assert r.status_code == 200, r.text
    iclient.post("/api/sync")
    cal = ICal.from_ical(fake.data("home", "r1.ics"))
    comps = cal.walk("VEVENT")
    master_c = next(c for c in comps if "RECURRENCE-ID" not in c)
    exdates = {d.dt.strftime("%Y%m%dT%H%M") for group in
               (master_c["EXDATE"] if isinstance(master_c["EXDATE"], list) else [master_c["EXDATE"]])
               for d in group.dts}
    assert {"20261111T1900", "20261125T1900"} <= exdates
    overrides = {c.decoded("RECURRENCE-ID").strftime("%m%d"): str(c["SUMMARY"]) for c in comps
                 if "RECURRENCE-ID" in c}
    assert overrides == {"1118": "Chor (Generalprobe)", "1202": "Chor (später)"}
    assert {str(c["UID"]) for c in comps} == {"r1@icloud"}
    # Rückweg stabil: keine doppelten oder verlorenen Vorkommen
    iclient.post("/api/sync")
    chor = [(e["title"], e["start"]) for e in events(iclient) if e["title"].startswith("Chor")]
    assert chor == [
        ("Chor", "2026-11-04T18:00:00Z"),
        ("Chor (Generalprobe)", "2026-11-18T17:00:00Z"),
        ("Chor (später)", "2026-12-02T19:00:00Z"),
        ("Chor", "2026-12-09T18:00:00Z"),
    ]


def test_invalid_sync_token_full_resync(iclient, fake):
    connect(iclient)
    fake.invalid_tokens = True
    del fake.res["home"]["a1.ics"]           # ohne Lösch-Eintrag
    assert iclient.post("/api/sync").json()["state"] == "idle"
    assert fake.rejected_tokens >= 1          # Token wurde wirklich abgelehnt → Voll-Sync
    assert "Flohmarkt" not in [e["title"] for e in events(iclient)]
    assert "Elternsprechtag" in [e["title"] for e in events(iclient)]


def test_server_without_sync_collection(iclient, fake):
    fake.no_sync_collection = True
    connect(iclient)
    assert "Chor (Generalprobe)" in [e["title"] for e in events(iclient)]
    del fake.res["home"]["s1.ics"]
    iclient.post("/api/sync")                 # jedes Mal Vollabgleich
    assert "Elternsprechtag" not in [e["title"] for e in events(iclient)]


def test_password_revoked(iclient, fake):
    connect(iclient)
    fake.password = "neue-pass-wort-xxxx"
    status = iclient.post("/api/sync").json()
    assert status["state"] == "error" and "neu verbinden" in status["last_error"]
    assert "Chor" in [e["title"] for e in events(iclient)]     # lokale Daten bleiben


def test_read_only_calendar_not_pushed(iclient, fake):
    connect(iclient)
    work = next(c["id"] for c in iclient.get("/api/calendars").json() if c["name"] == "Arbeit (geteilt)")
    assert iclient.post("/api/events", json={"title": "X", "start": "2026-11-26T10:00:00",
                                             "calendar_id": work}).status_code == 403
    assert not any(m == "PUT" for m, _ in fake.requests)


def test_explicit_default_is_kept(iclient, fake):
    """Ist schon ein Kalender eines anderen Kontos Standard, bleibt er es; erneutes Verbinden ändert nichts."""
    connect(iclient)
    local = next(c for c in iclient.get("/api/calendars").json() if c["provider"] == "local")
    iclient.put(f"/api/calendars/{local['id']}", json={"is_default": True})      # bewusst zurück auf lokal
    iclient.post("/api/accounts/icloud", json={"apple_id": "anna@icloud.com", "app_password": "abcd-efgh-ijkl-mnop"})
    iclient.post("/api/sync")
    defaults = [c["name"] for c in iclient.get("/api/calendars").json() if c["is_default"]]
    assert defaults == [local["name"]]
