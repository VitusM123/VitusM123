"""Smoke-Test: Das Gerüst ist importierbar und die Router sind registriert."""


def test_app_imports():
    from app.main import app

    assert app.title == "Familienplaner"
