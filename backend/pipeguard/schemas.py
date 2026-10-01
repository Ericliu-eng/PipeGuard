from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    database: str


class QualityCheckReport(BaseModel):
    """One check a reporting pipeline already evaluated for itself."""

    check_name: str = Field(min_length=1, max_length=120)
    status: Literal["PASS", "WARN", "FAIL"]
    metric_value: float
    threshold: float
    message: str = Field(min_length=1)


class RunReportRequest(BaseModel):
    """A finished run, reported by the pipeline that ran it.

    Only the checks a pipeline can evaluate from its own data belong here.
    Anything derived from run history — the row-count anomaly, for one — is
    computed on this side, because a pipeline cannot see its own past runs.
    """

    pipeline_name: str = Field(min_length=1, max_length=120)
    external_run_id: str = Field(min_length=1, max_length=200)
    status: Literal["SUCCESS", "FAILED"]
    started_at: datetime
    finished_at: datetime
    rows_processed: int = Field(ge=0)
    error_type: str | None = Field(default=None, max_length=120)
    error_message: str | None = None
    checks: list[QualityCheckReport] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ordering(self) -> Self:
        if self.started_at.tzinfo is None or self.finished_at.tzinfo is None:
            raise ValueError("started_at and finished_at must include a timezone")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self


class PipelineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_name: str
    external_run_id: str | None
    started_at: datetime
    finished_at: datetime | None
    status: Literal["RUNNING", "SUCCESS", "FAILED"]
    quality_status: Literal["NOT_EVALUATED", "PASS", "WARN", "FAIL"]
    rows_processed: int
    duration_ms: int | None
    error_type: str | None
    error_message: str | None


class QualityCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    check_name: str
    metric_value: float
    threshold: float
    status: str
    message: str
    created_at: datetime


class IncidentAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    summary: str
    severity: str
    likely_causes: str
    recommended_steps: str
    model_name: str
    created_at: datetime
