"""The FastAPI app loads and the health endpoint responds in Phase 0."""

from claims_auditor.api.app import app, healthz


def test_app_metadata() -> None:
    assert app.title == "Veritas — claims-auditor"


def test_healthz() -> None:
    assert healthz()["status"] == "ok"
