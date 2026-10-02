# PipeGuard

> A lightweight data-pipeline monitoring platform that detects execution and data-quality incidents, then produces actionable incident guidance.

[Live dashboard](https://pipeguard-dashboard-iiub.onrender.com) · [API documentation](https://pipeguard-fn1b.onrender.com/docs) · [API health](https://pipeguard-fn1b.onrender.com/health)

![PipeGuard dashboard showing run history and quality KPIs](docs/assets/pipeguard-dashboard.jpg)

> Free instances sleep when idle, so the first request can take about a minute.

## Why PipeGuard?

Individual developers and small data teams often run ingestion jobs without dedicated observability. A failed run, stale data, duplicate records, or a sudden row-count drop may not be noticed until a downstream user reports it. PipeGuard records each pipeline run, evaluates practical quality rules, and makes failures easy to inspect from one dashboard.

## Features

- Records successful and failed pipeline runs, including duration, processed rows, and error data.
- Runs four configurable data-quality checks: null rate, duplicate rate, freshness, and row-count anomaly.
- Persists run history, quality-check results, and incident analyses in PostgreSQL in production.
- Provides three reproducible demo scenarios over a synthetic dataset: normal, pipeline failure, and quality issue.
- Offers a Streamlit dashboard with run KPIs, run history, quality details, and incident analysis.
- Produces structured, rule-based incident summaries with severity, likely causes, and recommended next steps.
- Includes Docker configuration and GitHub Actions CI that lints and runs the suite against both SQLite and PostgreSQL.

## Architecture

```mermaid
flowchart LR
    U["Operator / Browser"] --> D["Streamlit Dashboard"]
    E["External Pipelines"] -->|"POST /runs<br/>X-API-Key"| A["FastAPI API"]
    D -->|"REST / HTTPS"| A

    A --> R["Run Ingestion<br/>validation · idempotency · retention"]
    A --> P["Synthetic Demo Runner"]
    A --> H["Run History<br/>filters · pagination · KPI summary"]
    A --> I["Rule-based Incident Analysis"]
    R --> Q["Quality Engine<br/>null · duplicate · freshness · row count"]
    P --> Q

    R --> S["SQLAlchemy ORM"]
    P --> S
    Q --> S
    H --> S
    I --> S
    S <--> DB[("PostgreSQL / Neon<br/>production")]
    S <--> LDB[("SQLite<br/>local development and tests")]
    M["Alembic Migrations"] --> DB
    M --> LDB
```

## Live demo

1. Open the [PipeGuard Dashboard](https://pipeguard-dashboard-iiub.onrender.com).
2. Select `normal`, `pipeline_failure`, or `quality_issue`.
3. Click **Run Pipeline**.
4. Review the resulting run, quality-check outcomes, and—when relevant—**Incident Analysis**.

> Render free instances may spin down after inactivity. The first request after idle time can take roughly a minute to start.

## Tech stack

| Area | Technology |
| --- | --- |
| Backend API | Python, FastAPI, SQLAlchemy |
| Dashboard | Streamlit, Pandas |
| Data store | PostgreSQL (Neon) via psycopg3, SQLite for local development |
| Quality checks | Configurable rule-based Python checks |
| Incident analysis | Deterministic rule-based summaries |
| Containers | Docker, Docker Compose |
| CI | GitHub Actions, Ruff, pytest |
| Hosting | Render |

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health check, including a database probe |
| `POST` | `/runs` | Report a run executed by an external pipeline |
| `POST` | `/runs/demo` | Run the demonstration pipeline |
| `GET` | `/runs` | List recent runs (backward-compatible array response) |
| `GET` | `/runs/page` | Filter and page through pipeline-run history |
| `GET` | `/runs/{id}` | Get one pipeline run |
| `GET` | `/runs/{id}/checks` | Get that run's quality-check results |
| `GET` | `/runs/{id}/analysis` | Get the stored incident analysis |
| `POST` | `/runs/{id}/analyze` | Create structured incident analysis |

`GET /health` runs a query against the database rather than returning a constant, and
answers `503` with `"status": "degraded"` when that query fails. A health check that
cannot fail is not a health check: an earlier constant `200` reported this service as
healthy for two months while the database behind it no longer existed.

`POST /runs` accepts a run from a real pipeline, so PipeGuard is not limited to the
bundled demo. The reporter sends what only it knows — its own timings, row count and
check results — and the row-count anomaly is computed here instead, from run history the
reporter has no way to see. An in-pipeline check asserts something about one batch; a
trend needs someone who remembers the previous ones.

Each report carries an `external_run_id`. Retrying the same pipeline/run ID returns the
stored run with `200` instead of creating a duplicate; the first report returns `201`.
Reusing that ID with different run data returns `409`, preventing a retry key from
silently overwriting or masking a different execution.
Execution state and data quality are deliberately separate: `status` says whether the
pipeline ran, while `quality_status` summarizes its checks as `PASS`, `WARN`, `FAIL`, or
`NOT_EVALUATED`.

`GET /runs/page` accepts exact `pipeline_name`, `status`, and `quality_status` filters plus
`limit` (1–200) and `offset`. It returns `items`, an accurate filtered `total`, stable
pagination metadata, and a filtered `summary` for the dashboard KPIs. Results are ordered
deterministically by newest start time and then by ID. As with offset pagination generally,
new runs inserted while browsing can shift later pages.

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0,
  "has_more": false,
  "summary": {
    "successful": 0,
    "failed": 0,
    "running": 0,
    "quality_incidents": 0
  }
}
```

The server reads the shared secret from `INGEST_API_KEY`. External callers should keep
their copy in their own secret store; the example below names that caller-side variable
`PIPEGUARD_API_KEY` so the two responsibilities stay clear.

```powershell
$env:PIPEGUARD_API_URL = "https://pipeguard-fn1b.onrender.com"
# Set PIPEGUARD_API_KEY through the pipeline's secret/environment configuration.

if (-not $env:PIPEGUARD_API_KEY) {
    throw "PIPEGUARD_API_KEY is not set"
}

$report = @'
{
  "pipeline_name": "market_data_lakehouse_pipeline",
  "external_run_id": "market-data-2026-09-28T12:00:00Z",
  "status": "SUCCESS",
  "started_at": "2026-09-28T12:00:00Z",
  "finished_at": "2026-09-28T12:00:04Z",
  "rows_processed": 500,
  "checks": [
    {
      "check_name": "not_null_ts",
      "status": "PASS",
      "metric_value": 0.0,
      "threshold": 0.0,
      "message": "market_bars.ts has no nulls."
    }
  ]
}
'@

Invoke-RestMethod `
    -Method Post `
    -Uri "$env:PIPEGUARD_API_URL/runs" `
    -Headers @{ "X-API-Key" = $env:PIPEGUARD_API_KEY } `
    -ContentType "application/json" `
    -Body $report
```

`POST /runs` requires `INGEST_API_KEY` in an `X-API-Key` header. With no key configured the
endpoint answers `503` rather than accepting writes: it stores rows on behalf of a caller,
so an unset secret has to fail closed.

```json
{
  "pipeline_name": "market_data_lakehouse_pipeline",
  "external_run_id": "market-data-2026-09-28T12:00:00Z",
  "status": "SUCCESS",
  "started_at": "2026-09-28T12:00:00Z",
  "finished_at": "2026-09-28T12:00:04Z",
  "rows_processed": 500,
  "checks": [
    {
      "check_name": "not_null_ts",
      "status": "PASS",
      "metric_value": 0.0,
      "threshold": 0.0,
      "message": "market_bars.ts has no nulls."
    }
  ]
}
```

`POST /runs/{id}/analyze` is idempotent: it returns `201` with a new analysis the first
time, and `200` with the stored analysis on later calls. A finished run and its checks no
longer change, so repeat calls would otherwise only duplicate rows.

An analysis explains each failed check in terms of what that check measures: a collapsed
row count points at upstream truncation or throttling, not at nulls and duplicates. Checks
reported by an external pipeline (`not_null`, `unique`, `range`, `foreign_key`,
`freshness`) are covered alongside PipeGuard's own; any other name falls back to generic
advice. `likely_causes` and `recommended_steps` are JSON arrays.

To simulate a quality issue, call:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/runs/demo?data_scenario=quality_failure"
```

To simulate a pipeline failure, call:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/runs/demo?simulate_failure=true"
```

## Run locally

### API

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn pipeguard.main:app --app-dir backend --reload
```

The API is then available at `http://127.0.0.1:8000`; OpenAPI docs are at `http://127.0.0.1:8000/docs`.

### Dashboard

In a second terminal, with the API running:

```powershell
python -m pip install -r dashboard/requirements.txt
$env:API_BASE_URL="http://127.0.0.1:8000"
streamlit run dashboard/app.py
```

Open `http://127.0.0.1:8501`.

## Run with Docker

```powershell
docker compose up --build
```

- API: `http://127.0.0.1:8000`
- Dashboard: `http://127.0.0.1:8501`

The Docker Compose setup applies Alembic migrations before starting the API and uses a
named volume for local SQLite persistence. Values in `.env`, including quality thresholds,
the retention limit and `INGEST_API_KEY`, are passed into the API container. Production
runs on Render with `DATABASE_URL` pointing at a Neon PostgreSQL instance. Any
`postgresql://` URL is normalized to the psycopg3 driver at startup, so the value
can be pasted from the provider unedited.

## Configuration

Copy `.env.example` to `.env` and adjust values as needed:

```text
DATABASE_URL=sqlite:///./pipeguard.db
DATABASE_CONNECT_TIMEOUT=10
NULL_RATE_THRESHOLD=0.05
DUPLICATE_RATE_THRESHOLD=0.01
FRESHNESS_HOURS_THRESHOLD=24
ROW_COUNT_DROP_THRESHOLD=0.30
ROW_COUNT_HISTORY_SIZE=5
RUN_RETENTION_LIMIT=500
INGEST_API_KEY=
```

`RUN_RETENTION_LIMIT` bounds stored history: after each run, runs older than the newest
500 *for that pipeline* are deleted along with their quality checks and incident analyses.
The budget is per pipeline rather than shared, so a pipeline that runs often cannot evict
the history of one that runs rarely. Set it to `0` to keep every run.

`INGEST_API_KEY` is the shared secret for `POST /runs`. Leaving it empty disables that
endpoint.

## Testing and CI

```powershell
pytest
ruff check backend dashboard migrations tests
```

The suite runs against in-memory SQLite by default. Point it at a real PostgreSQL
to exercise the production dialect and driver:

```powershell
docker run -d --name pipeguard-test-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=pipeguard_test -p 55432:5432 postgres:18
$env:TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:55432/pipeguard_test"
pytest
```

GitHub Actions runs Ruff and then the full suite twice, once against each backend.
Both runs matter: a SQLite-only suite never loads the PostgreSQL driver, so it
cannot catch a driver or dialect problem that would break production.

## Project structure

```text
backend/pipeguard/       FastAPI application, models, checks, and analysis service
dashboard/               Streamlit monitoring dashboard
tests/                   API, health, quality-check, and retention test suite
.github/workflows/       Continuous integration workflow
Dockerfile.api           API image definition
Dockerfile.dashboard     Dashboard image definition
docker-compose.yml       Local multi-container setup
```

## Database migrations

Schema changes are managed by Alembic:

```powershell
alembic upgrade head
```

The initial migration can adopt databases created by earlier PipeGuard releases, then
applies the quality-status and external-run-ID changes. Application startup no longer
executes DDL against whichever database happens to be configured.

The API container runs migrations before it starts the server. Both the migration engine
and the application engine give up on an unreachable database after
`DATABASE_CONNECT_TIMEOUT` seconds (default `10`): libpq would otherwise wait forever, and
a migration that never finishes is a server that never starts. A failed boot shows up as
an error in the platform logs instead of as requests that hang.

## Limitations and future work

- The bundled pipeline generates synthetic rows for deterministic demonstrations. Real pipelines
  integrate through `POST /runs`; a packaged client SDK and orchestrator-specific integrations are
  future work.
- Incident analysis uses deterministic rules, not a live LLM call.
- Reports may use multiple pipeline names, but pipeline registration and per-pipeline policies are
  future work.
- The ingest endpoint uses one shared API key; user accounts, rate limiting, schema-drift detection,
  and automated remediation are not yet included. `/health` can report a failure now, but nothing
  watches it and raises an alert — which
  is how an earlier outage went unnoticed for two months.
- Planned improvements include OpenAI-powered analysis, Slack/email alerts, configurable thresholds in the UI, and Prometheus/Grafana metrics.

