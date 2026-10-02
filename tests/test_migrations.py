import json
import os
import socket
import threading
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pipeguard.config import get_settings
from pipeguard.database import Base, normalize_database_url
from pipeguard.models import IncidentAnalysis
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


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


def test_existing_analyses_survive_the_move_to_json_columns(tmp_path: Path) -> None:
    # Production already holds analyses written as json.dumps() text, so the
    # migration must convert real rows, not just reshape an empty table. This
    # runs against PostgreSQL whenever TEST_DATABASE_URL points there, which is
    # where the ::json cast actually executes.
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'json.db').as_posix()}"
    engine = create_engine(normalize_database_url(url))
    _reset_schema(engine)

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0002_run_quality")

    with engine.begin() as connection:
        run_id = connection.execute(
            text(
                "INSERT INTO pipeline_runs (pipeline_name, started_at, status, rows_processed) "
                "VALUES ('legacy_pipeline', CURRENT_TIMESTAMP, 'FAILED', 0) RETURNING id"
            )
        ).scalar_one()
        analysis_id = connection.execute(
            text(
                "INSERT INTO incident_analyses (run_id, summary, severity, likely_causes, "
                "recommended_steps, model_name, created_at) VALUES (:run_id, 'Run failed.', "
                "'high', :causes, :steps, 'rule-based-fallback', CURRENT_TIMESTAMP) RETURNING id"
            ),
            {
                "run_id": run_id,
                "causes": '["RuntimeError", "Upstream service or network failure"]',
                "steps": '["Review the pipeline error message and logs."]',
            },
        ).scalar_one()

    command.upgrade(config, "head")

    with Session(engine) as session:
        analysis = session.get(IncidentAnalysis, analysis_id)
        assert analysis is not None
        assert analysis.likely_causes == ["RuntimeError", "Upstream service or network failure"]
        assert analysis.recommended_steps == ["Review the pipeline error message and logs."]

    # The downgrade has to hand back text that still parses, or rolling back
    # would strand every analysis written in the meantime.
    command.downgrade(config, "0002_run_quality")
    with engine.connect() as connection:
        stored = connection.execute(
            text("SELECT likely_causes FROM incident_analyses WHERE id = :id"),
            {"id": analysis_id},
        ).scalar_one()
    assert json.loads(stored) == ["RuntimeError", "Upstream service or network failure"]

    _reset_schema(engine)
    engine.dispose()


def _reset_schema(engine) -> None:
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_migrations_give_up_on_an_unresponsive_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A listener that completes the TCP handshake and then never answers is what
    # an unreachable database looks like to the client: libpq waits for a reply
    # that never comes. Migrations run before the server starts, so without a
    # connect timeout the deployment hangs forever instead of failing.
    with socket.socket() as silent_database:
        silent_database.bind(("127.0.0.1", 0))
        silent_database.listen()
        port = silent_database.getsockname()[1]

        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", f"postgresql://user:pass@127.0.0.1:{port}/db")
        monkeypatch.setattr(get_settings(), "database_connect_timeout", 1)

        outcome: dict[str, BaseException] = {}

        def upgrade() -> None:
            try:
                command.upgrade(config, "head")
            except OperationalError as exc:
                outcome["error"] = exc

        # Run in a thread with a ceiling, so a regression fails this test in
        # seconds rather than hanging the whole suite the way it hung startup.
        worker = threading.Thread(target=upgrade, daemon=True)
        worker.start()
        worker.join(timeout=10)

        assert not worker.is_alive(), "migrations hung on an unresponsive database"
        assert "error" in outcome
