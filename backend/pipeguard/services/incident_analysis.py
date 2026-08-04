import json
from datetime import UTC, datetime

from pipeguard.models import IncidentAnalysis, PipelineRun, QualityCheck, RunStatus


def build_incident_analysis(
    run: PipelineRun,
    checks: list[QualityCheck],
) -> IncidentAnalysis:
    failed_checks = [check for check in checks if check.status == "FAIL"]

    if run.status == RunStatus.failed:
        summary = run.error_message or "The pipeline run failed."
        severity = "high"
        likely_causes = [
            run.error_type or "Unknown pipeline error",
            "Upstream service or network failure",
        ]
        recommended_steps = [
            "Review the pipeline error message and logs.",
            "Check the upstream service availability.",
            "Retry the pipeline after verifying connectivity.",
        ]

    elif failed_checks:
        failed_names = [check.check_name for check in failed_checks]

        summary = (
            f"The pipeline completed, but {len(failed_checks)} "
            "data quality checks failed."
        )
        severity = "medium"
        likely_causes = [
            f"Failed quality checks: {', '.join(failed_names)}",
            "The source data may be incomplete, duplicated, stale, or unusually small.",
        ]
        recommended_steps = [
            "Review the failed check metrics and thresholds.",
            "Inspect the source data for nulls, duplicates, and stale timestamps.",
            "Compare the current row count with recent successful runs.",
        ]

    else:
        summary = "The pipeline completed successfully with no detected incidents."
        severity = "low"
        likely_causes = []
        recommended_steps = [
            "No immediate action is required.",
        ]

    return IncidentAnalysis(
        run_id=run.id,
        summary=summary,
        severity=severity,
        likely_causes=json.dumps(likely_causes),
        recommended_steps=json.dumps(recommended_steps),
        model_name="rule-based-fallback",
        created_at=datetime.now(UTC),
    )