from datetime import UTC, datetime

import pytest
from pipeguard.models import IncidentAnalysis, PipelineRun, QualityCheck, RunStatus
from pipeguard.services.incident_analysis import build_incident_analysis
from pipeguard.services.pipeline import prune_old_runs, run_demo_pipeline
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_prune_keeps_newest_runs_and_deletes_dependent_rows(db: Session) -> None:
    old_run = run_demo_pipeline(db)
    db.add(build_incident_analysis(old_run, []))
    db.commit()
    newest_run = run_demo_pipeline(db)

    prune_old_runs(db, limit=1)

    assert list(db.scalars(select(PipelineRun.id))) == [newest_run.id]
    # The cascade must take the old run's checks and analysis with it; a bulk
    # DELETE would leave these behind because the foreign keys have no
    # database-level ON DELETE CASCADE.
    assert _count(db, QualityCheck) == 4
    assert _count(db, IncidentAnalysis) == 0


def test_each_pipeline_keeps_its_own_history(db: Session) -> None:
    chatty = [_reported_run(db, "chatty_pipeline") for _ in range(3)]
    rare = _reported_run(db, "rare_pipeline")

    prune_old_runs(db, limit=2)

    remaining = set(db.scalars(select(PipelineRun.id)))
    # The budget is per pipeline: a pipeline that runs often must not evict the
    # history of one that runs rarely.
    assert rare.id in remaining
    assert chatty[0].id not in remaining
    assert len(remaining) == 3


def test_prune_is_disabled_when_limit_is_zero(db: Session) -> None:
    run_demo_pipeline(db)
    run_demo_pipeline(db)

    prune_old_runs(db, limit=0)

    assert _count(db, PipelineRun) == 2


def test_demo_runs_are_pruned_to_the_configured_limit(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pipeguard.services.pipeline.get_settings", _settings_with_limit(2))

    first = run_demo_pipeline(db)
    run_demo_pipeline(db)
    run_demo_pipeline(db)

    remaining = set(db.scalars(select(PipelineRun.id)))
    assert len(remaining) == 2
    assert first.id not in remaining


def _reported_run(db: Session, pipeline_name: str) -> PipelineRun:
    run = PipelineRun(
        pipeline_name=pipeline_name,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status=RunStatus.success,
        rows_processed=10,
        duration_ms=1,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _settings_with_limit(limit: int):
    from pipeguard.config import get_settings

    settings = get_settings().model_copy(update={"run_retention_limit": limit})
    return lambda: settings
