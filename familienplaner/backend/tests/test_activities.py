"""Freizeitaktivitäten: Quellen, Geocoding, Kategorien, Suche, Übernahme in den Kalender."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.domain.models import ActivityCategory, ActivitySource
from app.main import create_app
from app.providers.activities.dateparse import parse_datetime
from app.services.categorize import categorize
from tests.fake_sources import FakeSources

ICS = {"type": "ical", "name": "Stadt München", "config": {"url": "https://stadt.example/events.ics"}}
RSS = {"type": "rss", "name": "Museum", "config": {"url": "https://museum.example/feed.rss"}}
SEARCH = {"date_from": "2026-11-27", "date_to": "2026-12-07", "radius_km": 30}


@pytest.fixture
def fake():
    return FakeSources()


@pytest.fixture
def aclient(settings, fake):
    app = create_app(settings, start_scheduler=False, http_transport=fake.transport)
    app.state.sync.auto_sync = False
    app.state.activities.geo.min_interval = 0      # im Test nicht drosseln
    with TestClient(app) as c:
        c.put("/api/settings", json={"home": {"address": "München", "lat": 48.137, "lon": 11.575},
                                     "activity_radius_km": 30})
        yield c


def search(client, **kw):
    r = client.post("/api/activities/search", json={**SEARCH, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def titles(result):
    return [a["title"] for a in result["results"]]


# --- Bausteine ------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Konzert am 24.11.2026, 18:30 Uhr", ("2026-11-24T18:30", True)),
    ("Sa, 28.11. 10–16 Uhr", ("2026-11-28T10:00", True)),
    ("28. November 2026", ("2026-11-28T00:00", False)),
    ("am 3. Dez.", ("2026-12-03T00:00", False)),
    ("2026-12-05T09:15", ("2026-12-05T09:15", True)),
    ("Termin 15.01.", ("2027-01-15T00:00", False)),        # Jahreswechsel
    ("ohne Datum", None),
])
def test_parse_german_dates(text, expected):
    result = parse_datetime(text, today=date(2026, 11, 22))
    if expected is None:
        assert result is None
    else:
        assert (result[0].isoformat(timespec="minutes"), result[1]) == expected


def test_categorize():
    assert categorize("Tag der offenen Tür im Gymnasium") == ActivityCategory.OPEN_DAY
    assert categorize("Hochschulinformationstag TU") == ActivityCategory.OPEN_DAY
    assert categorize("Ausbildungsmesse 2026") == ActivityCategory.FAIR
    assert categorize("Weihnachtsmarkt am Rathaus") == ActivityCategory.MARKET
    assert categorize("Vernissage: Licht") == ActivityCategory.EXHIBITION
    assert categorize("Großer Preis", hints=["Music"]) == ActivityCategory.CONCERT
    assert categorize("Irgendwas") == ActivityCategory.OTHER
    assert categorize("Marktplatz-Führung") == ActivityCategory.MARKET     # Teilwort am Wortanfang


# --- Quellen und Suche ----------------------------------------------------------------------

def test_ical_source_search_radius_categories(aclient, fake):
    r = aclient.post("/api/activities/sources", json=ICS)
    assert r.status_code == 201, r.text
    src = r.json()
    assert src["last_error"] is None and src["last_count"] == 7   # 1 + 1 + 4 Führungen + Hamburg

    res = search(aclient)
    names = titles(res)
    assert "Tag der offenen Tür bei der Feuerwehr" in names
    assert "Weihnachtsmarkt am Rathaus" in names
    assert names.count("Museumsführung für Familien") == 2            # 28.11. und 5.12. im Zeitraum
    assert "Messe Hamburg" not in names                               # außerhalb des Umkreises
    assert "Abgesagtes Konzert" not in names
    by = {a["title"]: a for a in res["results"]}
    tdot = by["Tag der offenen Tür bei der Feuerwehr"]
    assert tdot["category"] == "open_day" and tdot["distance_km"] < 1 and tdot["url"] == "https://stadt.example/tdot"
    assert by["Weihnachtsmarkt am Rathaus"]["all_day"] and by["Weihnachtsmarkt am Rathaus"]["category"] == "market"
    assert res["center"]["label"] == "München"

    assert titles(search(aclient, categories=["open_day"])) == ["Tag der offenen Tür bei der Feuerwehr"]
    assert titles(search(aclient, query="markt")) == ["Weihnachtsmarkt am Rathaus"]
    # Großer Umkreis findet Hamburg
    assert "Messe Hamburg" in titles(search(aclient, radius_km=300, lat=53.0, lon=10.0))


def test_dedup_across_sources_and_rss_dates(aclient, fake):
    aclient.post("/api/activities/sources", json=ICS)
    r = aclient.post("/api/activities/sources", json=RSS).json()
    assert r["last_count"] == 2                      # Newsletter ohne Datum übersprungen
    names = titles(search(aclient))
    assert names.count("Tag der offenen Tür bei der Feuerwehr") == 1
    vern = next(a for a in search(aclient)["results"] if a["title"].startswith("Vernissage"))
    assert vern["title"] == "Vernissage: Licht & Schatten"       # Datum aus dem Titel entfernt
    assert vern["start"] == "2026-12-05T18:00:00Z" and vern["category"] == "exhibition"
    assert vern["venue"] == "Kunsthalle" and vern["distance_km"] < 2


def test_add_to_calendar_and_source_deletion(aclient, fake):
    aclient.post("/api/members", json={"name": "Tim", "color": "#669BBC"})
    aclient.post("/api/activities/sources", json=ICS)
    tdot = next(a for a in search(aclient)["results"] if a["title"].startswith("Tag der offenen"))
    r = aclient.post(f"/api/activities/{tdot['id']}/add-to-calendar", json={"member_ids": [1]})
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["start"] == "2026-11-28T09:00:00Z" and ev["end"] == "2026-11-28T15:00:00Z"
    assert ev["member_ids"] == [1] and ev["category"] == "open_day"
    assert "Feuerwache Nord" in ev["location"] and "https://stadt.example/tdot" in ev["description"]
    assert next(a for a in search(aclient)["results"] if a["id"] == tdot["id"])["event_id"] == ev["id"]

    wm = next(a for a in search(aclient)["results"] if a["title"].startswith("Weihnachtsmarkt"))
    ev2 = aclient.post(f"/api/activities/{wm['id']}/add-to-calendar", json={}).json()
    assert ev2["all_day"] and ev2["start"] == "2026-11-27" and ev2["end"] == "2026-12-24"

    src_id = aclient.get("/api/activities/sources").json()[0]["id"]
    assert aclient.delete(f"/api/activities/sources/{src_id}").status_code == 204
    assert aclient.get(f"/api/events/{ev['id']}").json()["title"] == "Tag der offenen Tür bei der Feuerwehr"


def test_ticketmaster_key_encrypted(aclient, fake):
    r = aclient.post("/api/activities/sources", json={"type": "ticketmaster", "name": "Ticketmaster",
                                                      "config": {"api_key": "tm-secret-key"}})
    assert r.status_code == 201 and r.json()["last_count"] == 1, r.text
    assert r.json()["config"]["api_key"] == "••••••••"
    with Session(aclient.app.state.engine) as s:
        stored = s.exec(select(ActivitySource)).one().config
        assert "tm-secret-key" not in str(stored)
    tm_req = next(q for q in fake.requests if q.url.host == "app.ticketmaster.com")
    assert tm_req.url.params["latlong"] == "48.1370,11.5750" and tm_req.url.params["unit"] == "km"
    hit = next(a for a in search(aclient)["results"] if a["title"].startswith("Kinderkonzert"))
    assert hit["category"] == "concert" and hit["venue"] == "Prinzregententheater"
    assert hit["image_url"] == "https://img/m.jpg" and 2 < hit["distance_km"] < 3
    # Name ändern ohne Schlüssel neu einzugeben → Schlüssel bleibt erhalten
    src_id = r.json()["id"]
    aclient.put(f"/api/activities/sources/{src_id}", json={"name": "TM", "config": {"api_key": "••••••••"}})
    assert aclient.post("/api/activities/refresh").json()[0]["error"] is None


def test_scraper_source(aclient, fake):
    cfg = {"url": "https://verein.example/termine", "item": "article.ev", "title": "h3", "date": ".when",
           "link": "a", "location": ".ort"}
    r = aclient.post("/api/activities/sources/test", json={"type": "scraper", "name": "Verein", "config": cfg})
    assert r.status_code == 200 and r.json()["count"] == 2, r.text
    aclient.post("/api/activities/sources", json={"type": "scraper", "name": "Verein", "config": cfg})
    res = search(aclient, include_unlocated=True)
    by = {a["title"]: a for a in res["results"]}
    assert by["Flohmarkt im Schulhof"]["start"] == "2026-12-05T08:00:00Z"
    assert by["Flohmarkt im Schulhof"]["url"] == "https://verein.example/termine/floh"
    assert by["Laternenbasteln"]["all_day"] and by["Laternenbasteln"]["distance_km"] is None
    assert "Laternenbasteln" not in titles(search(aclient))      # ohne Ort nur auf Wunsch


def test_errors_and_stale_removal(aclient, fake):
    bad = aclient.post("/api/activities/sources", json={"type": "ical", "name": "Kaputt",
                                                        "config": {"url": "https://stadt.example/404.ics"}})
    assert bad.status_code == 201 and "HTTP 404" in bad.json()["last_error"]
    assert aclient.post("/api/activities/sources", json={"type": "ical", "name": "X",
                                                         "config": {"url": "ftp://x"}}).status_code == 422
    aclient.post("/api/activities/sources", json=ICS)
    assert "Weihnachtsmarkt am Rathaus" in titles(search(aclient))
    fake.ics = fake.ics.replace("SUMMARY:Weihnachtsmarkt am Rathaus", "SUMMARY:Christkindlmarkt")
    results = aclient.post("/api/activities/refresh").json()
    assert {r["name"]: r["error"] is None for r in results} == {"Kaputt": False, "Stadt München": True}
    names = titles(search(aclient))
    assert "Christkindlmarkt" in names and "Weihnachtsmarkt am Rathaus" not in names


def test_search_center_resolution(aclient, fake, settings):
    aclient.post("/api/activities/sources", json=ICS)
    res = search(aclient, address="Augsburg", radius_km=20)
    assert res["center"]["label"] == "Augsburg" and res["results"] == []
    r = aclient.post("/api/activities/search", json={**SEARCH, "address": "Atlantis"})
    assert r.status_code == 422
    aclient.put("/api/settings", json={"home": {"address": "", "lat": None, "lon": None}})
    r = aclient.post("/api/activities/search", json=SEARCH)
    assert r.status_code == 422 and "Wohnort" in r.json()["detail"]
    geo = aclient.post("/api/activities/geocode", json={"address": "Marienplatz München"}).json()
    assert round(geo["lat"], 2) == 48.14
    # Nominatim: Cache verhindert doppelte Anfragen
    before = sum(1 for q in fake.requests if q.url.host == "nominatim.openstreetmap.org")
    aclient.post("/api/activities/geocode", json={"address": "marienplatz  münchen"})
    assert sum(1 for q in fake.requests if q.url.host == "nominatim.openstreetmap.org") == before
