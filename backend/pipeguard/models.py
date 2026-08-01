from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pipeguard.database import Base


class RunStatus(StrEnum):
    running = "RUNNING"
    success = "SUCCESS"
    failed = "FAILED"


class CheckStatus(StrEnum):
    passed = "PASS"
    warning = "WARN"
    failed = "FAIL"


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(120), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    rows_processed: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    quality_checks: Mapped[list["QualityCheck"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    incident_analyses: Mapped[list["IncidentAnalysis"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class QualityCheck(Base):
    __tablename__ = "quality_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    check_name: Mapped[str] = mapped_column(String(120))
    metric_value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    run: Mapped[PipelineRun] = relationship(back_populates="quality_checks")


class IncidentAnalysis(Base):
    __tablename__ = "incident_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))
    likely_causes: Mapped[str] = mapped_column(Text)
    recommended_steps: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    run: Mapped[PipelineRun] = relationship(back_populates="incident_analyses")

