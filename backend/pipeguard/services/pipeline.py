from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy.orm import Session

from pipeguard.models import PipelineRun, RunStatus

DEMO_ROWS = [
    {"event_id": 1, "value": 12.5},
    {"event_id": 2, "value": 15.0},
    {"event_id": 3, "value": 11.75},
]


def run_demo_pipeline(db: Session, *, simulate_failure: bool = False) -> PipelineRun:
    started_at = datetime.now(UTC)
    timer = perf_counter()
    run = PipelineRun(
        pipeline_name="demo_events_pipeline",
        started_at=started_at,
        status=RunStatus.running,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        if simulate_failure:
            raise RuntimeError("Simulated upstream API timeout")

        run.rows_processed = len(DEMO_ROWS)
        run.status = RunStatus.success
    except Exception as exc:
        run.status = RunStatus.failed
        run.error_type = type(exc).__name__
        run.error_message = str(exc)
    finally:
        run.finished_at = datetime.now(UTC)
        run.duration_ms = max(1, round((perf_counter() - timer) * 1000))
        db.add(run)
        db.commit()
        db.refresh(run)

    return run

