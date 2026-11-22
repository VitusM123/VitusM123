from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import NightMode
from app.services.backup_service import backup_database
from app.services.display_service import DisplayService

BERLIN = ZoneInfo("Europe/Berlin")


def test_builtin_themes_valid(client):
    themes = client.get("/api/themes").json()
    ids = {t["id"] for t in themes}
    assert {"light", "dark", "nordic", "pastel", "high-contrast", "eink-bw", "eink-color"} <= ids
    assert client.get("/api/themes/active").json()["id"] == "nordic"   # Standard aus config
    assert client.get("/api/themes/unknown").status_code == 404


def test_select_theme_and_settings(client):
    assert client.put("/api/settings/theme", json={"theme": "nope"}).status_code == 422
    assert client.put("/api/settings/theme", json={"theme": "dark"}).json()["theme"] == "dark"
    assert client.get("/api/themes/active").json()["id"] == "dark"
    r = client.put("/api/settings", json={"default_view": "family", "night_mode": {"enabled": False}})
    assert r.status_code == 200, r.text
    s = client.get("/api/settings").json()
    assert s["default_view"] == "family" and s["night_mode"]["enabled"] is False and s["theme"] == "dark"
    assert client.put("/api/settings", json={"day_starts": "25:00"}).status_code == 422
    assert s["show_header"] is True
    assert client.put("/api/settings", json={"show_header": False}).json()["show_header"] is False
    assert client.get("/api/settings").json()["show_header"] is False


def test_custom_theme_overrides_and_invalid_skipped(client, settings):
    d: Path = settings.custom_themes_dir
    d.mkdir(parents=True)
    (d / "mine.json").write_text('{"id":"mine","name":"Meins","mode":"light","tokens":{"bg":"#FFFFFF",'
                                 '"surface":"#FFFFFF","text":"#000000","text-muted":"#333333","accent":"#FF0000",'
                                 '"border":"#CCCCCC","today":"#FFFF00","weekend":"#EEEEEE"},"memberPalette":["#FF0000"]}')
    (d / "broken.json").write_text('{"id":"broken"}')
    themes = {t["id"]: t for t in client.get("/api/themes").json()}
    assert themes["mine"]["builtin"] is False
    assert "broken" not in themes


def test_auto_theme(app):
    from app.schemas import UserSettings
    user = UserSettings(auto_theme=True, day_theme="light", night_theme="dark",
                        day_starts="07:00", night_starts="19:00")
    assert app.state.themes.resolve_active_id(user, datetime(2026, 11, 22, 12, tzinfo=BERLIN)) == "light"
    assert app.state.themes.resolve_active_id(user, datetime(2026, 11, 22, 21, tzinfo=BERLIN)) == "dark"
    assert app.state.themes.resolve_active_id(user, datetime(2026, 11, 22, 6, tzinfo=BERLIN)) == "dark"


def test_night_mode_transitions_only():
    d = DisplayService(None)
    night = NightMode(enabled=True, off="22:30", on="06:30")
    assert d.tick(datetime(2026, 11, 22, 21, 0), night) is False      # Start tagsüber: nichts tun
    assert d.tick(datetime(2026, 11, 22, 22, 30), night) is True and d.screen_on is False
    d.set(screen_on=True)                                              # manuell aufgeweckt
    assert d.tick(datetime(2026, 11, 22, 23, 0), night) is False and d.screen_on is True
    assert d.tick(datetime(2026, 11, 23, 6, 30), night) is True and d.screen_on is True


def test_hardware_backlight(tmp_path):
    bl = tmp_path / "bl"
    bl.mkdir()
    (bl / "max_brightness").write_text("255")
    (bl / "brightness").write_text("255")
    (bl / "bl_power").write_text("0")
    d = DisplayService(bl)
    d.set(screen_on=False, brightness=50)
    assert (bl / "brightness").read_text() == "128" and (bl / "bl_power").read_text() == "1"


def test_display_api_and_ws(client):
    with client.websocket_connect("/ws") as ws:
        r = client.put("/api/display", json={"screen_on": False})
        assert r.json()["screen_on"] is False
        msg = ws.receive_json()
        assert msg["type"] == "display.changed" and msg["payload"]["screen_on"] is False
        client.post("/api/display/wake")
        assert ws.receive_json()["payload"]["screen_on"] is True
        client.post("/api/events", json={"title": "X", "start": "2026-11-24T10:00:00"})
        assert ws.receive_json()["type"] == "events.changed"


def test_backup_rotation(client, settings):
    for _ in range(3):
        backup_database(settings.database.path, settings.database.backup_dir, keep=2)
    assert len(list(settings.database.backup_dir.glob("*.db"))) <= 2


def test_sync_endpoint_without_accounts(client):
    r = client.post("/api/sync")
    assert r.status_code == 200 and r.json()["state"] == "idle"


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
