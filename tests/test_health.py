from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pipeguard.database import Base, get_db
from pipeguard.main import app
from sqlalchemy.exc import OperationalError


class _UnreachableSession:
    """Stands in for a session whose database has gone away."""

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def close(self) -> None:
        pass


def test_health_reports_ok_when_the_database_answers(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"


def test_health_reports_degraded_when_the_database_is_unreachable(
    client: TestClient,
) -> None:
    def unreachable_db() -> Generator[_UnreachableSession, None, None]:
        yield _UnreachableSession()

    app.dependency_overrides[get_db] = unreachable_db

    response = client.get("/health")

    # The endpoint used to return a constant "ok", so a dashboard watching it
    # stayed green while the database behind it no longer existed. It has to be
    # able to fail, and to fail with a status code a monitor can act on.
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"] == "unavailable"


def test_startup_survives_an_unreachable_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable_create_all(**kwargs: Any) -> None:
        raise OperationalError("CREATE TABLE", {}, Exception("connection refused"))

    monkeypatch.setattr(Base.metadata, "create_all", unreachable_create_all)

    # Entering the context runs the lifespan. It must complete rather than raise
    # or block, otherwise no route is served at all and the outage looks like
    # requests that never return.
    with TestClient(app) as test_client:
        assert test_client.get("/health").status_code in (200, 503)
