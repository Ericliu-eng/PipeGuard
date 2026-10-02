"""Store incident analysis causes and steps as JSON, not as encoded text.

Revision ID: 0003_analysis_json
Revises: 0002_run_quality
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_analysis_json"
down_revision: str | Sequence[str] | None = "0002_run_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Both columns have always held json.dumps() output, so on PostgreSQL every
# existing value already parses as JSON and the cast converts it in place. On
# SQLite the JSON type is stored as text either way; batch mode rebuilds the
# table there because SQLite cannot alter a column's type directly.
_COLUMNS = ("likely_causes", "recommended_steps")


def upgrade() -> None:
    with op.batch_alter_table("incident_analyses") as batch:
        for column in _COLUMNS:
            batch.alter_column(
                column,
                type_=sa.JSON(),
                existing_type=sa.Text(),
                existing_nullable=False,
                postgresql_using=f"{column}::json",
            )


def downgrade() -> None:
    with op.batch_alter_table("incident_analyses") as batch:
        for column in _COLUMNS:
            batch.alter_column(
                column,
                type_=sa.Text(),
                existing_type=sa.JSON(),
                existing_nullable=False,
                postgresql_using=f"{column}::text",
            )
