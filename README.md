# PipeGuard

> A lightweight data-pipeline monitoring platform that detects execution and data-quality incidents, then produces actionable incident guidance.

[Open the live dashboard](https://pipeguard-dashboard-iiub.onrender.com) · [Open the API](https://pipeguard-fn1b.onrender.com) · [API health check](https://pipeguard-fn1b.onrender.com/health) · [Interactive API docs](https://pipeguard-fn1b.onrender.com/docs)

## Why PipeGuard?

Individual developers and small data teams often run ingestion jobs without dedicated observability. A failed run, stale data, duplicate records, or a sudden row-count drop may not be noticed until a downstream user reports it. PipeGuard records each pipeline run, evaluates practical quality rules, and makes failures easy to inspect from one dashboard.

## Features

- Records successful and failed pipeline runs, including duration, processed rows, and error data.
- Runs four configurable data-quality checks: null rate, duplicate rate, freshness, and row-count anomaly.
- Persists run history, quality-check results, and incident analyses in PostgreSQL in production.
- Provides three reproducible demo scenarios: normal, pipeline failure, and quality issue.
- Offers a Streamlit dashboard with run KPIs, run history, quality details, and incident analysis.
- Produces structured, rule-based incident summaries with severity, likely causes, and recommended next steps.
- Includes Docker configuration and GitHub Actions CI for linting and automated tests.

## Architecture

```mermaid
flowchart LR
    D["Streamlit Dashboard"] -->|"HTTPS"| A["FastAPI API"]
    A --> P["Demo Pipeline Runner"]
    P --> Q["Quality Checks"]
    Q --> A
    A --> DB[("PostgreSQL")]
    A --> I["Incident Analyzer"]
    I --> DB
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
| Incident analysis | Structured rule-based fallback |
| Containers | Docker, Docker Compose |
| CI | GitHub Actions, Ruff, pytest |
| Hosting | Render |

## API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health check, including a database probe |
| `POST` | `/runs/demo` | Run the demonstration pipeline |
| `GET` | `/runs` | List pipeline-run history |
| `GET` | `/runs/{id}` | Get one pipeline run |
| `GET` | `/runs/{id}/checks` | Get that run's quality-check results |
| `GET` | `/runs/{id}/analysis` | Get the stored incident analysis |
| `POST` | `/runs/{id}/analyze` | Create structured incident analysis |

`GET /health` runs a query against the database rather than returning a constant, and
answers `503` with `"status": "degraded"` when that query fails. A health check that
cannot fail is not a health check: an earlier constant `200` reported this service as
healthy for two months while the database behind it no longer existed.

`POST /runs/{id}/analyze` is idempotent: it returns `201` with a new analysis the first
time, and `200` with the stored analysis on later calls. A finished run and its checks no
longer change, so repeat calls would otherwise only duplicate rows.

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

The Docker Compose setup uses a named volume for local SQLite persistence. Production
runs on Render with `DATABASE_URL` pointing at a Neon PostgreSQL instance. Any
`postgresql://` URL is normalized to the psycopg3 driver at startup, so the value
can be pasted from the provider unedited.

## Configuration

Copy `.env.example` to `.env` and adjust values as needed:

```text
DATABASE_URL=sqlite:///./pipeguard.db
NULL_RATE_THRESHOLD=0.05
DUPLICATE_RATE_THRESHOLD=0.01
FRESHNESS_HOURS_THRESHOLD=24
ROW_COUNT_DROP_THRESHOLD=0.30
ROW_COUNT_HISTORY_SIZE=5
RUN_RETENTION_LIMIT=500
```

`RUN_RETENTION_LIMIT` bounds stored history: after each run, older runs beyond the newest
500 are deleted along with their quality checks and incident analyses. Set it to `0` to
keep every run.

## Testing and CI

```powershell
pytest
ruff check backend tests
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
tests/                   API and quality-check test suite
.github/workflows/       Continuous integration workflow
Dockerfile.api           API image definition
Dockerfile.dashboard     Dashboard image definition
docker-compose.yml       Local multi-container setup
```

## Limitations and future work

- Incident analysis currently uses a deterministic rule-based fallback, not a live LLM call.
- The demo supports one sample pipeline; multi-pipeline registration is future work.
- Authentication, alerting, schema-drift detection, and automated remediation are not yet included.
- Planned improvements include OpenAI-powered analysis, Slack/email alerts, configurable thresholds in the UI, and Prometheus/Grafana metrics.

