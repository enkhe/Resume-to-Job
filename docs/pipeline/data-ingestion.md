# Data Ingestion

The **Data Ingestion** page ([1_Data_Ingestion.py](../../pages/1_Data_Ingestion.py)) loads jobs
from three sources, embeds their descriptions, and upserts them into SQLite in batches of 200.

## Sources

### 1. CSV upload
Columns: `id`, `title`, `company`, `description` (required); `location`, `source` (optional).
Invalid rows (missing required fields) are reported and skipped.

### 2. Generic API endpoint
Any JSON endpoint that returns a list of records under `data` / `jobs` / `items` / `results`.
Follows `links.next` / `meta.next` pagination (e.g. Arbeitnow ~100/page) up to a job limit.
Implemented in [api_client.py](../../src/adapters/inbound/api_provider/api_client.py).

### 3. JSearch (RapidAPI) — IT jobs
The primary source for this project. Fetches IT postings from `jsearch.p.rapidapi.com`.
Each request returns ~10 jobs; the free plan is ~200 requests/month, so requests are precious.
Implemented in [jsearch_client.py](../../src/adapters/inbound/api_provider/jsearch_client.py) and
[jsearch_job_parser.py](../../src/adapters/inbound/api_provider/jsearch_job_parser.py).

The parser handles both `/search` (`data: [...]`) and `/search-v2` (`data: {jobs, cursor}`)
envelopes, maps fields to the normalized record shape, and dedupes by `job_id`.

## Bulk harvesting (the budget-safe path)

For building the corpus, use the harvester rather than the UI:
[testing/scripts/harvest_jobs_jsearch.py](../../testing/scripts/harvest_jobs_jsearch.py).

```bash
# See the plan and how many requests it would spend, WITHOUT calling the API:
python testing/scripts/harvest_jobs_jsearch.py --dry-run

# Fetch up to N new requests, then ingest everything:
export JSEARCH_API_KEY=...your-rapidapi-key...
python testing/scripts/harvest_jobs_jsearch.py --max-requests 20

# Rebuild the DB + master CSV from cached raw responses (NO API calls):
python testing/scripts/harvest_jobs_jsearch.py --ingest-only
```

**Why it never wastes a paid request:**
- Every response is written to `data/jsearch_raw/` **before** anything else, so embedding/DB
  failures cost zero re-fetches; re-ingest is free.
- A **manifest** records every `(query, page)` already fetched, so re-runs never re-spend.
- A hard `--max-requests` cap plus the live `x-ratelimit-requests-remaining` header stop the run
  before the monthly quota is exhausted (`--min-remaining` floor).

The query matrix targets IT-grad roles (22 roles × 12 locations). Harvested jobs carry the role
query that found them — that becomes the label source for the [classifier](../mlops/training-pipeline.md).

## Ingestion internals

`IngestJobsBatchUseCase` ([ingest_jobs_batch.py](../../src/application/use_cases/ingest_jobs_batch.py)):

1. Deduplicate by `id`.
2. Embed all descriptions in a single `embed_texts` call.
3. Upsert in chunks of 200 (`INSERT ... ON CONFLICT DO UPDATE`).

Emits `ingest_jobs_batch.started` / `.completed` JSON log events
(see [observability](../operations/observability.md)).
