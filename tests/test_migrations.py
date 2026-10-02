import socket
import threading
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pipeguard.config import get_settings
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError


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
