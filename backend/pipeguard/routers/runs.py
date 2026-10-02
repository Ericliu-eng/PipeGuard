from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session, aliased

from pipeguard.database import get_db
from pipeguard.models import (
    IncidentAnalysis,
    PipelineRun,
    QualityCheck,
    RunQualityStatus,
    RunStatus,
)
from pipeguard.schemas import (
    IncidentAnalysisResponse,
    PipelineRunPageResponse,
    PipelineRunResponse,
    PipelineRunSummaryResponse,
    QualityCheckResponse,
    RunReportRequest,
)
from pipeguard.security import require_ingest_key
from pipeguard.services.incident_analysis import build_incident_analysis
from pipeguard.services.ingest import RunReportConflictError, record_reported_run
from pipeguard.services.pipeline import DataScenario, run_demo_pipeline

router = APIRouter(prefix="/runs", tags=["runs"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=PipelineRunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_ingest_key)],
)
def report_run(report: RunReportRequest, db: DbSession, response: Response) -> PipelineRun:
    """Record a run that an external pipeline already executed.

    The caller sends what only it knows — its own timings, row count and check
    results. The row-count anomaly is added here, from run history the caller
    has no way to see.
    """
    try:
        run, created = record_reported_run(db, report)
    except RunReportConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return run


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
    statement = (
        select(PipelineRun)
        .order_by(PipelineRun.started_at.desc(), PipelineRun.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))


@router.get("/page", response_model=PipelineRunPageResponse)
def list_run_page(
    db: DbSession,
    pipeline_name: str | None = Query(default=None, min_length=1, max_length=120),
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    quality_status: Annotated[RunQualityStatus | None, Query()] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PipelineRunPageResponse:
    filters = []
    if pipeline_name is not None:
        if not pipeline_name.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="pipeline_name must not be blank",
            )
        filters.append(PipelineRun.pipeline_name == pipeline_name)
    if run_status is not None:
        filters.append(PipelineRun.status == run_status)
    if quality_status is not None:
        filters.append(PipelineRun.quality_status == quality_status)

    filtered_runs = select(PipelineRun).where(*filters).cte("filtered_runs")
    aggregates = select(
        func.count(filtered_runs.c.id).label("total"),
        func.coalesce(
            func.sum(case((filtered_runs.c.status == RunStatus.success, 1), else_=0)),
            0,
        ).label("successful"),
        func.coalesce(
            func.sum(case((filtered_runs.c.status == RunStatus.failed, 1), else_=0)),
            0,
        ).label("failed"),
        func.coalesce(
            func.sum(case((filtered_runs.c.status == RunStatus.running, 1), else_=0)),
            0,
        ).label("running"),
        func.coalesce(
            func.sum(
                case(
                    (filtered_runs.c.quality_status == RunQualityStatus.failed, 1),
                    else_=0,
                )
            ),
            0,
        ).label("quality_incidents"),
    ).cte("run_aggregates")
    paged_runs = (
        select(filtered_runs)
        .order_by(filtered_runs.c.started_at.desc(), filtered_runs.c.id.desc())
        .offset(offset)
        .limit(limit)
        .cte("paged_runs")
    )
    paged_run = aliased(PipelineRun, paged_runs)
    statement = (
        select(
            paged_run,
            aggregates.c.total,
            aggregates.c.successful,
            aggregates.c.failed,
            aggregates.c.running,
            aggregates.c.quality_incidents,
        )
        .select_from(aggregates.outerjoin(paged_runs, true()))
        .order_by(paged_runs.c.started_at.desc(), paged_runs.c.id.desc())
    )
    rows = db.execute(statement).all()
    first_row = rows[0]
    items = [row[0] for row in rows if row[0] is not None]

    return PipelineRunPageResponse(
        items=items,
        total=first_row.total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < first_row.total,
        summary=PipelineRunSummaryResponse(
            successful=first_row.successful,
            failed=first_row.failed,
            running=first_row.running,
            quality_incidents=first_row.quality_incidents,
        ),
    )


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

    if run.status == RunStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run is still in progress",
        )

    existing = _latest_analysis(db, run_id)

    if existing is not None:
        # A finished run and its checks never change, so re-analyzing would only
        # duplicate rows. Return the stored analysis instead of creating another.
        response.status_code = status.HTTP_200_OK
        return existing

    statement = select(QualityCheck).where(QualityCheck.run_id == run_id).order_by(QualityCheck.id)
    checks = list(db.scalars(statement))

    analysis = build_incident_analysis(run, checks)

    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return analysis
