from datetime import UTC, datetime

from pipeguard.models import PipelineRun, QualityCheck, RunStatus
from pipeguard.services.incident_analysis import build_incident_analysis

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def _run(status: RunStatus = RunStatus.success, **fields: object) -> PipelineRun:
    return PipelineRun(
        id=1,
        pipeline_name="market_data_lakehouse_pipeline",
        started_at=NOW,
        status=status,
        rows_processed=0,
        **fields,
    )


def _check(name: str, status: str = "FAIL") -> QualityCheck:
    return QualityCheck(
        run_id=1,
        check_name=name,
        metric_value=1.0,
        threshold=0.0,
        status=status,
        message=f"{name} failed.",
        created_at=NOW,
    )


def test_a_row_count_drop_is_explained_as_a_row_count_drop() -> None:
    analysis = build_incident_analysis(_run(), [_check("row_count_anomaly")])

    advice = " ".join(analysis.likely_causes + analysis.recommended_steps).lower()
    assert "row count" in advice
    assert "upstream" in advice
    # The old advice was written for the demo data set and sent the reader to
    # look for nulls and duplicates — neither of which a collapsed row count
    # involves, and this is the one check the monitoring side owns.
    assert "null" not in advice
    assert "duplicate" not in advice


def test_checks_reported_by_an_external_pipeline_get_specific_advice() -> None:
    analysis = build_incident_analysis(_run(), [_check("range")])

    assert any("parsing" in step.lower() for step in analysis.recommended_steps)


def test_an_unknown_check_gets_generic_advice_instead_of_an_error() -> None:
    analysis = build_incident_analysis(_run(), [_check("custom_business_rule")])

    assert analysis.severity == "medium"
    assert analysis.likely_causes == ["A quality check failed against its threshold."]
    assert "custom_business_rule" in analysis.summary


def test_repeated_and_overlapping_checks_are_reported_once() -> None:
    # A pipeline may report one not_null per column, and not_null shares its
    # advice with null_rate. The reader should see each cause and step once.
    checks = [_check("not_null"), _check("not_null"), _check("null_rate")]

    analysis = build_incident_analysis(_run(), checks)

    assert analysis.summary.endswith("2 data quality checks failed: not_null, null_rate.")
    assert len(analysis.likely_causes) == 1
    assert len(analysis.recommended_steps) == len(set(analysis.recommended_steps))


def test_a_single_failed_check_reads_in_the_singular() -> None:
    analysis = build_incident_analysis(_run(), [_check("freshness")])

    assert analysis.summary.endswith("1 data quality check failed: freshness.")


def test_warnings_alone_are_not_reported_as_an_incident() -> None:
    analysis = build_incident_analysis(_run(), [_check("row_count_anomaly", status="WARN")])

    assert analysis.severity == "low"


def test_a_failed_run_takes_precedence_over_its_checks() -> None:
    run = _run(status=RunStatus.failed, error_type="TimeoutError", error_message="API timed out")

    analysis = build_incident_analysis(run, [_check("row_count_anomaly")])

    assert analysis.severity == "high"
    assert analysis.likely_causes[0] == "TimeoutError"
