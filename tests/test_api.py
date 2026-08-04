from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_pipeline_success_and_run_detail(client: TestClient) -> None:
    created = client.post("/runs/demo")

    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "SUCCESS"
    assert payload["rows_processed"] == 3
    assert payload["error_message"] is None

    detail = client.get(f"/runs/{payload['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == payload["id"]

    checks = client.get(f"/runs/{payload['id']}/checks")
    assert checks.status_code == 200
    assert {check["check_name"] for check in checks.json()} == {
        "null_rate",
        "duplicate_rate",
        "freshness",
        "row_count_anomaly",
    }
    assert {check["status"] for check in checks.json()} == {"PASS", "WARN"}


def test_demo_pipeline_failure_is_persisted(client: TestClient) -> None:
    created = client.post("/runs/demo?simulate_failure=true")

    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "FAILED"
    assert payload["rows_processed"] == 0
    assert payload["error_type"] == "RuntimeError"
    assert "timeout" in payload["error_message"].lower()

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert len(runs.json()) == 1


def test_unknown_run_returns_404(client: TestClient) -> None:
    response = client.get("/runs/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_quality_failure_persists_four_failed_checks(client: TestClient) -> None:
    client.post("/runs/demo")
    created = client.post("/runs/demo?data_scenario=quality_failure")

    assert created.status_code == 201
    assert created.json()["status"] == "SUCCESS"
    checks = client.get(f"/runs/{created.json()['id']}/checks").json()
    assert len(checks) == 4
    assert {check["status"] for check in checks} == {"FAIL"}
