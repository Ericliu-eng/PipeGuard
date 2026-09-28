import pytest
from pipeguard.models import IncidentAnalysis, PipelineRun, QualityCheck
from pipeguard.services.incident_analysis import build_incident_analysis
from pipeguard.services.pipeline import _prune_old_runs, run_demo_pipeline
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_prune_keeps_newest_runs_and_deletes_dependent_rows(db: Session) -> None:
    old_run = run_demo_pipeline(db)
    db.add(build_incident_analysis(old_run, []))
    db.commit()
    newest_run = run_demo_pipeline(db)

    _prune_old_runs(db, limit=1)

    assert list(db.scalars(select(PipelineRun.id))) == [newest_run.id]
    # The cascade must take the old run's checks and analysis with it; a bulk
    # DELETE would leave these behind because the foreign keys have no
    # database-level ON DELETE CASCADE.
    assert _count(db, QualityCheck) == 4
    assert _count(db, IncidentAnalysis) == 0


def test_prune_is_disabled_when_limit_is_zero(db: Session) -> None:
    run_demo_pipeline(db)
    run_demo_pipeline(db)

    _prune_old_runs(db, limit=0)

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


def _settings_with_limit(limit: int):
    from pipeguard.config import get_settings

    settings = get_settings().model_copy(update={"run_retention_limit": limit})
    return lambda: settings
