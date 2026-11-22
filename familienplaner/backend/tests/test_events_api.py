from datetime import date


def _week(client, start="2026-11-23T00:00:00", end="2026-11-30T00:00:00", **params):
    r = client.get("/api/events", params={"start": start, "end": end, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_default_calendar_seeded(client):
    cals = client.get("/api/calendars").json()
    assert len(cals) == 1
    assert cals[0]["name"] == "Familie" and cals[0]["is_default"] and cals[0]["provider"] == "local"


def test_create_timed_event_local_time(client, members):
    r = client.post("/api/events", json={
        "title": "Zahnarzt", "start": "2026-11-24T14:00:00", "end": "2026-11-24T15:00:00",
        "member_ids": [members[0]],
    })
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["start"] == "2026-11-24T13:00:00Z"   # 14:00 Berlin = 13:00 UTC
    assert ev["member_ids"] == [members[0]]
    assert len(_week(client)) == 1
    assert _week(client, members=[members[1]]) == []


def test_all_day_event_returns_dates(client):
    r = client.post("/api/events", json={"title": "Ausflug", "start": "2026-11-28", "all_day": True})
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["start"] == "2026-11-28" and ev["end"] == "2026-11-29"
    # Nur am 28. sichtbar, nicht am 27.
    assert _week(client, start="2026-11-27T00:00:00", end="2026-11-28T00:00:00") == []
    assert len(_week(client, start="2026-11-28T00:00:00", end="2026-11-29T00:00:00")) == 1


def test_validation_errors(client):
    r = client.post("/api/events", json={"title": "X", "start": "2026-11-24T15:00:00", "end": "2026-11-24T14:00:00"})
    assert r.status_code == 422
    r = client.post("/api/events", json={"title": "X", "start": "2026-11-24"})
    assert r.status_code == 422   # zeitgebunden ohne Uhrzeit
    r = client.post("/api/events", json={"title": "X", "start": "2026-11-24T10:00:00", "rrule": "FREQ=BAD"})
    assert r.status_code == 422
    r = client.post("/api/events", json={"title": "X", "start": "2026-11-24T10:00:00", "member_ids": [999]})
    assert r.status_code == 404


def test_update_keeps_duration_and_members(client, members):
    ev = client.post("/api/events", json={
        "title": "Training", "start": "2026-11-24T17:00:00", "end": "2026-11-24T18:30:00", "member_ids": [members[1]],
    }).json()
    r = client.put(f"/api/events/{ev['id']}", json={"start": "2026-11-25T16:00:00"})
    assert r.status_code == 200, r.text
    upd = r.json()
    assert upd["start"] == "2026-11-25T15:00:00Z" and upd["end"] == "2026-11-25T16:30:00Z"
    assert upd["member_ids"] == [members[1]]


def test_recurring_series_single_occurrence_edit_and_delete(client, members):
    ev = client.post("/api/events", json={
        "title": "Schwimmen", "start": "2026-11-23T16:00:00", "end": "2026-11-23T17:00:00",
        "rrule": "FREQ=DAILY;COUNT=5", "member_ids": [members[2]],
    }).json()
    occ = _week(client)
    assert len(occ) == 5 and all(o["recurring"] for o in occ)

    # Dienstag verschieben (nur dieses Vorkommen)
    tuesday = occ[1]["start"]
    r = client.put(f"/api/events/{ev['id']}", params={"occurrence_start": tuesday},
                   json={"start": "2026-11-24T18:00:00", "title": "Schwimmen (später)"})
    assert r.status_code == 200, r.text
    override_id = r.json()["id"]
    assert override_id != ev["id"]
    occ = _week(client)
    assert len(occ) == 5
    assert [o["title"] for o in occ].count("Schwimmen (später)") == 1

    # Gleiches Vorkommen erneut ändern -> dieselbe Einzeländerung
    r = client.put(f"/api/events/{ev['id']}", params={"occurrence_start": tuesday}, json={"location": "Hallenbad"})
    assert r.json()["id"] == override_id
    assert r.json()["series_id"] == ev["id"]

    # Mittwoch absagen
    r = client.delete(f"/api/events/{ev['id']}", params={"occurrence_start": occ[2]["start"]})
    assert r.status_code == 204
    assert len(_week(client)) == 4

    # Einzeländerung direkt löschen -> Vorkommen bleibt abgesagt (kein Wiederauftauchen)
    assert client.delete(f"/api/events/{override_id}").status_code == 204
    occ = _week(client)
    assert len(occ) == 3 and all(o["title"] == "Schwimmen" for o in occ)

    # Ungültiges Vorkommen
    r = client.delete(f"/api/events/{ev['id']}", params={"occurrence_start": "2026-11-24T09:00:00Z"})
    assert r.status_code == 404

    # Ganze Serie löschen entfernt auch die Einzeländerung
    assert client.delete(f"/api/events/{ev['id']}").status_code == 204
    assert _week(client) == []


def test_all_day_series_occurrence_delete(client):
    ev = client.post("/api/events", json={
        "title": "Müll", "start": "2026-11-23", "all_day": True, "rrule": "FREQ=WEEKLY;BYDAY=MO,TH",
    }).json()
    occ = _week(client)
    assert [o["start"] for o in occ] == ["2026-11-23", "2026-11-26"]
    assert client.delete(f"/api/events/{ev['id']}", params={"occurrence_start": "2026-11-26"}).status_code == 204
    assert [o["start"] for o in _week(client)] == ["2026-11-23"]


def test_calendar_default_member_and_hidden(client, members):
    cal = client.post("/api/calendars", json={"name": "Schule Lena", "color": "#7FB069",
                                              "default_member_id": members[2]}).json()
    client.post("/api/events", json={"title": "Elternabend", "calendar_id": cal["id"],
                                     "start": "2026-11-26T19:00:00"})
    occ = _week(client)
    assert occ[0]["member_ids"] == [members[2]] and occ[0]["color"] == "#7FB069"
    client.put(f"/api/calendars/{cal['id']}", json={"visible": False})
    assert _week(client) == []
    assert len(_week(client, calendars=[cal["id"]])) == 1


def test_family_table(client, members):
    client.post("/api/events", json={"title": "Fußball", "start": "2026-11-24T17:00:00", "member_ids": [members[1]]})
    client.post("/api/events", json={"title": "Oma", "start": "2026-11-25", "end": "2026-11-27", "all_day": True})
    client.post("/api/events", json={"title": "Kino", "start": "2026-11-26T20:00:00",
                                     "member_ids": [members[0], members[1]]})
    r = client.get("/api/family-table", params={"start": "2026-11-23", "days": 7})
    assert r.status_code == 200, r.text
    table = r.json()
    assert [m["name"] for m in table["members"]] == ["Anna", "Ben", "Lena"]
    days = {d["date"]: d for d in table["days"]}
    assert len(days) == 7
    assert [e["title"] for e in days["2026-11-24"]["cells"][str(members[1])]] == ["Fußball"]
    assert [e["title"] for e in days["2026-11-25"]["unassigned"]] == ["Oma"]
    assert [e["title"] for e in days["2026-11-26"]["unassigned"]] == ["Oma"]   # mehrtägig
    assert days["2026-11-27"]["unassigned"] == []
    assert len(days["2026-11-26"]["cells"][str(members[0])]) == 1


def test_window_limits(client):
    r = client.get("/api/events", params={"start": "2026-01-01T00:00:00", "end": "2028-01-01T00:00:00"})
    assert r.status_code == 422
    r = client.get("/api/family-table", params={"start": str(date(2026, 11, 1)), "days": 100})
    assert r.status_code == 422


def test_last_local_calendar_cannot_be_deleted(client):
    cal_id = client.get("/api/calendars").json()[0]["id"]
    assert client.delete(f"/api/calendars/{cal_id}").status_code == 409
