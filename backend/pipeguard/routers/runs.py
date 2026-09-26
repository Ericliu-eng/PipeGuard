from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeguard.database import get_db
from pipeguard.models import IncidentAnalysis, PipelineRun, QualityCheck
from pipeguard.schemas import (
    IncidentAnalysisResponse,
    PipelineRunResponse,
    QualityCheckResponse,
)
from pipeguard.services.incident_analysis import build_incident_analysis
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

def _latest_analysis(db: Session, run_id: int) -> IncidentAnalysis | None:
    statement = (
        select(IncidentAnalysis)
        .where(IncidentAnalysis.run_id == run_id)
        .order_by(IncidentAnalysis.id.desc())
        .limit(1)
    )
    return db.scalars(statement).first()


@router.get("/{run_id}/analysis", response_model=IncidentAnalysisResponse)
def get_run_analysis(run_id: int, db: DbSession) -> IncidentAnalysis:
    if db.get(PipelineRun, run_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )

    analysis = _latest_analysis(db, run_id)

    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found",
        )

    return analysis


@router.post(
    "/{run_id}/analyze",
    response_model=IncidentAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
def analyze_run(run_id: int, db: DbSession, response: Response) -> IncidentAnalysis:
    run = db.get(PipelineRun, run_id)

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )

    existing = _latest_analysis(db, run_id)

    if existing is not None:
        # A finished run and its checks never change, so re-analyzing would only
        # duplicate rows. Return the stored analysis instead of creating another.
        response.status_code = status.HTTP_200_OK
        return existing

    statement = (
        select(QualityCheck)
        .where(QualityCheck.run_id == run_id)
        .order_by(QualityCheck.id)
    )
    checks = list(db.scalars(statement))

    analysis = build_incident_analysis(run, checks)

    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return analysis