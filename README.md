# PipeGuard

PipeGuard is a lightweight data pipeline monitoring platform for individual developers and
small data teams. It records pipeline runs, exposes run history through an API, and will add
data-quality checks and AI-assisted incident analysis in later milestones.

## Current milestone

The first runnable slice includes:

- FastAPI application with a health endpoint
- SQLite-backed run persistence (PostgreSQL-ready via `DATABASE_URL`)
- Core tables for pipeline runs, quality checks, and incident analyses
- Configurable Null, Duplicate, Freshness, and Row-count anomaly checks
- Demo pipeline with reproducible run and data-quality failure modes
- Run list, detail, and quality-check APIs
- Automated API tests

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn pipeguard.main:app --app-dir backend --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API documentation.

## Demo flow

Create a successful run:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/runs/demo"
```

Create a failed run:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/runs/demo?simulate_failure=true"
```

Create a run with deterministic data-quality failures:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/runs/demo?data_scenario=quality_failure"
```

List runs:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/runs"
```

View a run's quality-check results:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/runs/1/checks"
```

## Test

```powershell
pytest
ruff check .
```

## Project structure

```text
backend/pipeguard/   FastAPI application and domain logic
docs/                Product and schema notes
tests/               API tests
```

## Next milestone

Build the Streamlit dashboard for the latest status, run history, and quality-check results.
