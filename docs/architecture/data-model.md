# Data Model

## Domain entities

Defined in [src/domain/entities](../../src/domain/entities). All are frozen dataclasses.

### `Job`
| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Unique. JSearch `job_id`, CSV `id`, or provider slug. |
| `title` | `str` | Required. |
| `company` | `str` | Required. |
| `description` | `str` | Required; embedded for similarity. |
| `location` | `str \| None` | e.g. `"Chicago, Illinois"` or `"Remote"`. |
| `source` | `str \| None` | `"jsearch"`, `"api"`, `"demo"`, etc. |
| `embedding` | `tuple[float, ...] \| None` | 384-dim `all-MiniLM-L6-v2` vector. |

### `Resume`
`file_name`, `text`, `embedding` (384-dim). Built from an uploaded PDF.

### `Recommendation`
`ResumeRecommendation(resume_score, resume_feedback, top_jobs)` where each `RecommendedJob`
has `job_id`, `title`, `company`, `fit_score`, `rationale`.

## SQLite schema

The `jobs` table ([SQLiteJobRepository](../../src/adapters/outbound/persistence/sqlite_job_repository.py)):

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    description TEXT,
    location    TEXT,
    source      TEXT,
    embedding   TEXT,           -- JSON-encoded list[float]
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Writes use `INSERT ... ON CONFLICT(id) DO UPDATE` (idempotent upserts), in batches of 200.
Default path: `data/jobs.db` (override with `JOB_DB_PATH`). The DB is git-ignored.

## Harvested-data layout (the training corpus)

```text
data/
  jobs.db                 # runtime SQLite (git-ignored)
  jobs_master.csv         # committable export of all unique harvested jobs
  jsearch_raw/
    manifest.json         # every (query, page) fetched + the role that found each file
    <hash>.json           # raw JSearch responses (one per request) — re-ingestible for free
```

The `manifest.json` role labels are what make the harvested jobs a **labeled dataset** for the
classifier — see [training pipeline](../mlops/training-pipeline.md).

## Model registry layout

```text
models/job_role_classifier/
  registry.json           # {"latest": "vN", "versions": [{version, trained_at, accuracy, f1_macro, ...}]}
  v1/
    model.joblib          # serialized sklearn Pipeline (the "pkl")
    metrics.json          # accuracy, F1, per-class report, confusion matrix, CV scores
    metadata.json         # version, trained_at, classes, sklearn version, data fingerprint
  v2/ ...
```

The app reads `registry.json["latest"]` to load the active model. See the
[model card](../mlops/model-card.md).
