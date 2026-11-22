from app.config import Settings


def test_yaml_and_env_precedence(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "display:\n  theme: pastel\n  default_view: month\nlocale:\n  timezone: Europe/Vienna\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FP_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("FP_DISPLAY__THEME", "dark")
    s = Settings()
    assert s.display.theme == "dark"            # Umgebungsvariable schlägt YAML
    assert s.display.default_view == "month"    # Rest aus YAML bleibt erhalten
    assert s.locale.timezone == "Europe/Vienna"


def test_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FP_CONFIG_FILE", str(tmp_path / "nope.yaml"))
    s = Settings()
    assert s.display.mode == "lcd"
    assert s.sync.interval_minutes == 5
