# Problem statement

Small data teams often operate scheduled API or database ingestion jobs without dedicated
observability infrastructure. Failures, stale data, unexpected row counts, and rising null or
duplicate rates may remain unnoticed until a downstream user reports them. Raw logs then make
root-cause investigation slow and inconsistent.

PipeGuard provides a small, locally reproducible monitoring layer for one demonstration pipeline.
The MVP records each run, evaluates four configurable data-quality rules, and presents the result
through an API and dashboard. Failed runs can later be summarized into structured troubleshooting
guidance by an LLM, with a deterministic fallback when no model is available.

## MVP boundaries

Included:

- One demonstration pipeline
- Run history and failure details
- Null, duplicate, freshness, and row-count checks
- Dashboard for current state and history
- Structured incident explanation

Not included:

- Authentication or multi-user permissions
- Multiple pipeline registration
- Automated remediation
- Complex anomaly-detection models
- Slack or email alerting

