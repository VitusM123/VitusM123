import pytest
from fastapi.testclient import TestClient

from app.config import DatabaseSettings, LocaleSettings, SecuritySettings, Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("FP_CONFIG_FILE", str(tmp_path / "missing.yaml"))
    return Settings(
        database=DatabaseSettings(path=tmp_path / "test.db", backup_dir=tmp_path / "backups"),
        security=SecuritySettings(secret_key_file=tmp_path / "secret.key"),
        locale=LocaleSettings(timezone="Europe/Berlin"),
    )


@pytest.fixture
def app(settings):
    return create_app(settings, start_scheduler=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def members(client):
    ids = []
    for name, color in (("Anna", "#E4572E"), ("Ben", "#29335C"), ("Lena", "#F3A712")):
        r = client.post("/api/members", json={"name": name, "color": color})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids
