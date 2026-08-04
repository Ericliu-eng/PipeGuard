from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeguard.database import get_db
from pipeguard.models import PipelineRun, QualityCheck
from pipeguard.schemas import PipelineRunResponse, QualityCheckResponse
from pipeguard.services.pipeline import DataScenario, run_demo_pipeline

router = APIRouter(prefix="/runs", tags=["runs"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("/demo", response_model=PipelineRunResponse, status_code=status.HTTP_201_CREATED)
def create_demo_run(
    db: DbSession,
    simulate_failure: bool = Query(default=False),
    data_scenario: Annotated[DataScenario, Query()] = "normal",
) -> PipelineRun:
    return run_demo_pipeline(
        db,
        simulate_failure=simulate_failure,
        data_scenario=data_scenario,
    )


@router.get("", response_model=list[PipelineRunResponse])
def list_runs(db: DbSession, limit: int = Query(default=50, ge=1, le=200)) -> list[PipelineRun]:
    statement = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
    return list(db.scalars(statement))


@router.get("/{run_id}", response_model=PipelineRunResponse)
def get_run(run_id: int, db: DbSession) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("/{run_id}/checks", response_model=list[QualityCheckResponse])
def get_run_checks(run_id: int, db: DbSession) -> list[QualityCheck]:
    if db.get(PipelineRun, run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    statement = select(QualityCheck).where(QualityCheck.run_id == run_id).order_by(QualityCheck.id)
    return list(db.scalars(statement))
