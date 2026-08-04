# Data model

## `pipeline_runs`

One record per pipeline execution. Stores timing, status, processed row count, and normalized error
details.

## `quality_checks`

One record per check evaluated for a run. Stores the measured value, configured threshold, status,
and a human-readable message. The MVP writes `null_rate`, `duplicate_rate`, `freshness`, and
`row_count_anomaly` results for each completed demonstration run.

## `incident_analyses`

Stores structured incident summaries associated with failed runs, including severity, likely
causes, recommended steps, and model provenance.

Relationships:

```text
pipeline_runs 1 ---- * quality_checks
pipeline_runs 1 ---- * incident_analyses
```
