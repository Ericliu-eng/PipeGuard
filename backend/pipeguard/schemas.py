from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str


class PipelineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pipeline_name: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    rows_processed: int
    duration_ms: int | None
    error_type: str | None
    error_message: str | None

