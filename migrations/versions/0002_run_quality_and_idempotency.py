"""Add run quality state and idempotent external identifiers.

Revision ID: 0002_run_quality
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_run_quality"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("pipeline_runs")}

    if "external_run_id" not in columns:
        op.add_column(
            "pipeline_runs",
            sa.Column("external_run_id", sa.String(length=200), nullable=True),
        )
    if "quality_status" not in columns:
        op.add_column(
            "pipeline_runs",
            sa.Column(
                "quality_status",
                sa.String(length=20),
                nullable=False,
                server_default="NOT_EVALUATED",
            ),
        )

    op.execute(
        sa.text(
            """
            UPDATE pipeline_runs
            SET quality_status = CASE
                WHEN status <> 'SUCCESS' THEN 'NOT_EVALUATED'
                WHEN EXISTS (
                    SELECT 1 FROM quality_checks
                    WHERE quality_checks.run_id = pipeline_runs.id
                      AND quality_checks.status = 'FAIL'
                ) THEN 'FAIL'
                WHEN EXISTS (
                    SELECT 1 FROM quality_checks
                    WHERE quality_checks.run_id = pipeline_runs.id
                      AND quality_checks.status = 'WARN'
                ) THEN 'WARN'
                WHEN EXISTS (
                    SELECT 1 FROM quality_checks
                    WHERE quality_checks.run_id = pipeline_runs.id
                ) THEN 'PASS'
                ELSE 'NOT_EVALUATED'
            END
            """
        )
    )

    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("pipeline_runs")}
    if "uq_pipeline_runs_pipeline_external_run_id" not in index_names:
        op.create_index(
            "uq_pipeline_runs_pipeline_external_run_id",
            "pipeline_runs",
            ["pipeline_name", "external_run_id"],
            unique=True,
        )
    if "ix_pipeline_runs_baseline_lookup" not in index_names:
        op.create_index(
            "ix_pipeline_runs_baseline_lookup",
            "pipeline_runs",
            ["pipeline_name", "status", "quality_status", "started_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_baseline_lookup", table_name="pipeline_runs")
    op.drop_index("uq_pipeline_runs_pipeline_external_run_id", table_name="pipeline_runs")
    with op.batch_alter_table("pipeline_runs") as batch_op:
        batch_op.drop_column("quality_status")
        batch_op.drop_column("external_run_id")
