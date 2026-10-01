from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migrations_build_the_current_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-test.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("pipeline_runs")}
    indexes = {index["name"] for index in inspector.get_indexes("pipeline_runs")}

    assert {"external_run_id", "report_fingerprint", "quality_status"} <= columns
    assert "uq_pipeline_runs_pipeline_external_run_id" in indexes
    assert "ix_pipeline_runs_baseline_lookup" in indexes
    engine.dispose()
