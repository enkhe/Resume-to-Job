# Project Structure

```text
app.py                      # Streamlit home + logging setup
pages/                      # Streamlit pages (numbered = sidebar order)
  1_Data_Ingestion.py
  2_Dashboard.py
  3_Job_Search.py
  4_Job_Matching.py
  5_Model_Ops.py

src/
  domain/
    entities/               # Job, Resume, Recommendation
    services/               # similarity (cosine)
  application/
    use_cases/              # ingest, match, recommend, search, dashboard
  ports/output/             # JobRepository, EmbeddingService, RecommendationService, JobClassifier
  adapters/
    inbound/
      streamlit/            # one *_app.py per page
      api_provider/         # jsearch_client/parser, generic api_client/parser
      file_upload/          # CSV + PDF parsers
    outbound/
      persistence/          # SQLiteJobRepository
      embedding/            # SentenceTransformers adapter
      llm/                  # OpenAI-compatible recommendation adapter
      ml/                   # SklearnJobClassifierAdapter (loads the trained model)
      search/               # TfidfKeywordSearch (lexical)
      logging/              # structured JSON logging

ml/                         # MLOps training pipeline
  dataset.py                # build labeled dataset from harvest manifest
  train_role_classifier.py  # train -> evaluate -> version -> register

models/job_role_classifier/ # model registry (registry.json + vN/ artifacts)

data/                       # runtime + harvested data
  jobs.db                   # SQLite (git-ignored)
  jobs_master.csv           # committable export of harvested jobs
  jsearch_raw/              # raw JSearch responses + manifest.json (the labeled source)

tests/                      # pytest unit suite
testing/                    # scripts (harvest, eval, helpers) + sample data + OBSERVABILITY.md
docs/                       # this documentation set
.github/workflows/ci-cd.yml # CI/CD pipeline
Dockerfile, docker-compose.yml, .dockerignore
DEPLOYMENT.md, .env.example, requirements*.txt
```

## Conventions
- **Hexagonal**: depend on ports, not adapters. New tech = new adapter implementing a port.
- **One use case per task**; use cases emit structured log events.
- **Streamlit pages are thin** — each `pages/N_*.py` just calls a `streamlit_app()` in
  `src/adapters/inbound/streamlit/`.
- **Models are versioned artifacts**, never overwritten; the registry's `latest` pointer selects
  the served model.
