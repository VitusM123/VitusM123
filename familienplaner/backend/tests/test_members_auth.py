def test_member_crud_and_order(client, members):
    r = client.put("/api/members/order", json=[members[2], members[0], members[1]])
    assert [m["name"] for m in r.json()] == ["Lena", "Anna", "Ben"]
    r = client.put(f"/api/members/{members[0]}", json={"name": "Anna-Lena", "color": "#000000"})
    assert r.json()["name"] == "Anna-Lena"
    assert client.post("/api/members", json={"name": "X", "color": "red"}).status_code == 422
    assert client.delete(f"/api/members/{members[1]}").status_code == 204
    assert len(client.get("/api/members").json()) == 2


def test_member_delete_removes_assignments(client, members):
    client.post("/api/events", json={"title": "A", "start": "2026-11-24T10:00:00", "member_ids": members[:2]})
    client.delete(f"/api/members/{members[0]}")
    ev = client.get("/api/events", params={"start": "2026-11-24T00:00:00", "end": "2026-11-25T00:00:00"}).json()
    assert ev[0]["member_ids"] == [members[1]]


def test_pin_flow(client):
    assert client.get("/api/auth/status").json() == {"pin_set": False, "authenticated": False}
    # Ohne PIN ist der Admin-Bereich offen (Ersteinrichtung)
    assert client.post("/api/members", json={"name": "A", "color": "#111111"}).status_code == 201

    assert client.post("/api/auth/setup", json={"pin": "12"}).status_code == 422
    assert client.post("/api/auth/setup", json={"pin": "2468"}).status_code == 200
    assert client.post("/api/auth/setup", json={"pin": "1111"}).status_code == 409
    assert client.get("/api/auth/status").json()["authenticated"] is True

    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.post("/api/members", json={"name": "B", "color": "#111111"}).status_code == 401
    # Termine bleiben ohne PIN bedienbar
    assert client.post("/api/events", json={"title": "T", "start": "2026-11-24T10:00:00"}).status_code == 201

    assert client.post("/api/auth/login", json={"pin": "0000"}).status_code == 401
    assert client.post("/api/auth/login", json={"pin": "2468"}).status_code == 200
    assert client.post("/api/members", json={"name": "B", "color": "#111111"}).status_code == 201

    # PIN-Änderung macht alte Sitzungen ungültig
    old_cookie = client.cookies.get("fp_session")
    assert client.post("/api/auth/change-pin", json={"current_pin": "2468", "new_pin": "13579"}).status_code == 200
    client.cookies.clear()
    client.cookies.set("fp_session", old_cookie)
    assert client.post("/api/members", json={"name": "C", "color": "#111111"}).status_code == 401


def test_login_throttle(client):
    client.post("/api/auth/setup", json={"pin": "2468"})
    client.cookies.clear()
    for _ in range(5):
        assert client.post("/api/auth/login", json={"pin": "0000"}).status_code == 401
    r = client.post("/api/auth/login", json={"pin": "2468"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
