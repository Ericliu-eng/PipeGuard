from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeguard.config import get_settings
from pipeguard.models import PipelineRun, QualityCheck, RunStatus
from pipeguard.services.quality_checks import (
    QualityCheckResult,
    check_duplicate_rate,
    check_freshness,
    check_null_rate,
    check_row_count_anomaly,
)

DataScenario = Literal["normal", "quality_failure"]


def demo_rows(scenario: DataScenario, *, now: datetime) -> list[dict[str, object]]:
    if scenario == "quality_failure":
        stale_time = now - timedelta(hours=48)
        return [
            {"event_id": 1, "value": None, "event_time": stale_time},
            {"event_id": 1, "value": None, "event_time": stale_time},
        ]

    return [
        {"event_id": 1, "value": 12.5, "event_time": now - timedelta(minutes=5)},
        {"event_id": 2, "value": 15.0, "event_time": now - timedelta(minutes=3)},
        {"event_id": 3, "value": 11.75, "event_time": now - timedelta(minutes=1)},
    ]


def run_demo_pipeline(
    db: Session,
    *,
    simulate_failure: bool = False,
    data_scenario: DataScenario = "normal",
) -> PipelineRun:
    started_at = datetime.now(UTC)
    timer = perf_counter()
    run = PipelineRun(
        pipeline_name="demo_events_pipeline",
        started_at=started_at,
        status=RunStatus.running,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        if simulate_failure:
            raise RuntimeError("Simulated upstream API timeout")

        rows = demo_rows(data_scenario, now=started_at)
        run.rows_processed = len(rows)
        _persist_quality_checks(db, run=run, rows=rows, now=started_at)
        run.status = RunStatus.success
    except Exception as exc:
        run.status = RunStatus.failed
        run.error_type = type(exc).__name__
        run.error_message = str(exc)
    finally:
        run.finished_at = datetime.now(UTC)
        run.duration_ms = max(1, round((perf_counter() - timer) * 1000))
        db.add(run)
        db.commit()
        db.refresh(run)

    prune_old_runs(db, limit=get_settings().run_retention_limit)

    return run


def prune_old_runs(db: Session, *, limit: int) -> None:
    """Keep only the newest ``limit`` runs *per pipeline*, deleting older ones.

    The budget is per pipeline rather than global: with one shared limit, a
    pipeline that runs often would evict the history of one that runs rarely,
    and the rare pipeline is the one whose history you still want.

    Runs are removed through the ORM rather than a bulk DELETE so the
    ``delete-orphan`` cascade also removes their quality checks and incident
    analyses. A bulk statement would bypass that cascade and orphan those rows,
    because the foreign keys carry no database-level ``ON DELETE CASCADE``.
    """
    if limit <= 0:
        return

    # One query per pipeline rather than a single windowed one: the number of
    # distinct pipelines is small, and this reads plainly on both backends.
    stale_runs: list[PipelineRun] = []
    for pipeline_name in db.scalars(select(PipelineRun.pipeline_name).distinct()):
        newest = (
            select(PipelineRun.id)
            .where(PipelineRun.pipeline_name == pipeline_name)
            .order_by(PipelineRun.started_at.desc(), PipelineRun.id.desc())
            .limit(limit)
            .subquery()
        )
        stale_runs.extend(
            db.scalars(
                select(PipelineRun).where(
                    PipelineRun.pipeline_name == pipeline_name,
                    PipelineRun.id.not_in(select(newest.c.id)),
                )
            )
        )

    if not stale_runs:
        return

    for stale_run in stale_runs:
        db.delete(stale_run)
    db.commit()


def _persist_quality_checks(
    db: Session,
    *,
    run: PipelineRun,
    rows: list[dict[str, object]],
    now: datetime,
) -> None:
    settings = get_settings()
    historical_counts = list(
        db.scalars(
            select(PipelineRun.rows_processed)
            .where(
                PipelineRun.pipeline_name == run.pipeline_name,
                PipelineRun.status == RunStatus.success,
            )
            .where(PipelineRun.id != run.id)
            .order_by(PipelineRun.started_at.desc())
            .limit(settings.row_count_history_size)
        )
    )
    results = [
        check_null_rate(rows, field="value", threshold=settings.null_rate_threshold),
        check_duplicate_rate(
            rows,
            key_fields=("event_id",),
            threshold=settings.duplicate_rate_threshold,
        ),
        check_freshness(rows, threshold_hours=settings.freshness_hours_threshold, now=now),
        check_row_count_anomaly(
            len(rows),
            historical_counts=historical_counts,
            threshold=settings.row_count_drop_threshold,
        ),
    ]
    db.add_all([_to_quality_check(run.id, result, now=now) for result in results])


def _to_quality_check(
    run_id: int, result: QualityCheckResult, *, now: datetime
) -> QualityCheck:
    return QualityCheck(
        run_id=run_id,
        check_name=result.check_name,
        metric_value=result.metric_value,
        threshold=result.threshold,
        status=result.status,
        message=result.message,
        created_at=now,
    )
