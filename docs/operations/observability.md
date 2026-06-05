# Observability

## Structured logging
The app emits **one JSON object per log line** to stdout — ideal for containers and log pipelines.
Configured once by `configure_logging()` in [app.py](../../app.py); implemented in
[structured_logging.py](../../src/adapters/outbound/logging/structured_logging.py).

Each event line looks like:
```json
{"timestamp":"2026-06-05T07:28:06Z","level":"INFO","logger":"src.application.use_cases.match_jobs_to_resume",
 "message":"match_jobs_to_resume.completed","event":"match_jobs_to_resume.completed",
 "fields":{"ok":true,"match_count":5,"scored_count":1139,"top_score":0.6354,"duration_ms":372.5}}
```

`LOG_LEVEL` (default `INFO`) controls verbosity.

## Event catalog
| Event | Emitted by | Key fields |
|-------|-----------|------------|
| `ingest_jobs_batch.started` / `.completed` | ingest | `input_count`, `unique_count`, `batches`, `duration_ms` |
| `match_jobs_to_resume.started` / `.completed` / `.failed` | matching | `scored_count`, `skipped_no_embedding`, `top_score` |
| `recommend_jobs_with_ai.started` / `.provider_completed` / `.completed` / `.failed` | AI | `candidate_count`, `resume_score`, `ai_duration_ms` |

## Offline evaluation
`testing/scripts/pipeline_eval.py` runs the pipeline against sample fixtures and reports metrics
without the UI:
```bash
python testing/scripts/clear_jobs_table.py
python testing/scripts/pipeline_eval.py            # add --run-ai if an LLM key is set
```
See [testing/OBSERVABILITY.md](../../testing/OBSERVABILITY.md) for the original runbook.

## Model observability
The **Model Ops** page exposes model metrics (accuracy, F1, per-class report, confusion matrix),
the version registry, and the data→model freshness check. Each model version's `metrics.json`
is the durable record. See [model card](../mlops/model-card.md).

## Helper scripts
| Script | Purpose |
|--------|---------|
| `testing/scripts/check_job_embeddings.py` | Verify stored jobs have embeddings. |
| `testing/scripts/clear_jobs_table.py` | Empty the `jobs` table. |
| `testing/scripts/harvest_jobs_jsearch.py` | Harvest + ingest JSearch jobs (budget-safe). |
