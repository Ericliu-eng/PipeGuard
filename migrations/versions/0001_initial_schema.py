"""Create the original PipeGuard schema.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create missing tables while adopting databases made by create_all."""
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "pipeline_runs" not in existing:
        op.create_table(
            "pipeline_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pipeline_name", sa.String(length=120), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("rows_processed", sa.Integer(), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_type", sa.String(length=120), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
        )
        op.create_index("ix_pipeline_runs_pipeline_name", "pipeline_runs", ["pipeline_name"])
        op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"])
        op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])

    if "quality_checks" not in existing:
        op.create_table(
            "quality_checks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("check_name", sa.String(length=120), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=False),
            sa.Column("threshold", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        )
        op.create_index("ix_quality_checks_run_id", "quality_checks", ["run_id"])

    if "incident_analyses" not in existing:
        op.create_table(
            "incident_analyses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("likely_causes", sa.Text(), nullable=False),
            sa.Column("recommended_steps", sa.Text(), nullable=False),
            sa.Column("model_name", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        )
        op.create_index("ix_incident_analyses_run_id", "incident_analyses", ["run_id"])


def downgrade() -> None:
    op.drop_table("incident_analyses")
    op.drop_table("quality_checks")
    op.drop_table("pipeline_runs")
