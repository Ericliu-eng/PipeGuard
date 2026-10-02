from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pipeguard.models import PipelineRun, RunStatus
from sqlalchemy.orm import Session


def test_demo_pipeline_success_and_run_detail(client: TestClient) -> None:
    created = client.post("/runs/demo")

    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "SUCCESS"
    assert payload["quality_status"] == "WARN"
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
    assert payload["quality_status"] == "NOT_EVALUATED"
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
    assert created.json()["quality_status"] == "FAIL"
    checks = client.get(f"/runs/{created.json()['id']}/checks").json()
    assert len(checks) == 4
    assert {check["status"] for check in checks} == {"FAIL"}


def test_analyze_failed_run_returns_rule_based_analysis(client: TestClient) -> None:
    created = client.post("/runs/demo?simulate_failure=true")

    assert created.status_code == 201
    run_id = created.json()["id"]

    response = client.post(f"/runs/{run_id}/analyze")

    assert response.status_code == 201

    payload = response.json()

    assert payload["run_id"] == run_id
    assert payload["severity"] == "high"
    assert payload["model_name"] == "rule-based"
    assert "timeout" in payload["summary"].lower()
    # Real lists now, not JSON encoded into a string: the old assertions here
    # were substring checks against that string, which matched any text at all.
    assert payload["likely_causes"][0] == "RuntimeError"
    assert any("upstream service" in step.lower() for step in payload["recommended_steps"])


def test_analyze_unknown_run_returns_404(client: TestClient) -> None:
    response = client.post("/runs/999/analyze")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_repeated_analyze_returns_the_stored_analysis(client: TestClient) -> None:
    run_id = client.post("/runs/demo?simulate_failure=true").json()["id"]

    created = client.post(f"/runs/{run_id}/analyze")
    repeated = client.post(f"/runs/{run_id}/analyze")

    assert created.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["id"] == created.json()["id"]


def test_get_analysis_returns_404_until_the_run_is_analyzed(client: TestClient) -> None:
    run_id = client.post("/runs/demo?simulate_failure=true").json()["id"]

    missing = client.get(f"/runs/{run_id}/analysis")

    assert missing.status_code == 404
    assert missing.json() == {"detail": "Analysis not found"}

    created = client.post(f"/runs/{run_id}/analyze")
    stored = client.get(f"/runs/{run_id}/analysis")

    assert stored.status_code == 200
    assert stored.json()["id"] == created.json()["id"]


def test_get_analysis_for_unknown_run_returns_404(client: TestClient) -> None:
    response = client.get("/runs/999/analysis")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_running_run_cannot_be_analyzed(client: TestClient, db: Session) -> None:
    run = PipelineRun(
        pipeline_name="still_running_pipeline",
        started_at=datetime.now(UTC),
        status=RunStatus.running,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    response = client.post(f"/runs/{run.id}/analyze")

    assert response.status_code == 409
    assert response.json() == {"detail": "Run is still in progress"}
