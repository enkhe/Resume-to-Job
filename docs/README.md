# Resume-to-Job — Documentation

Project documentation for **Resume-to-Job**, an MLOps job-search application built for
AI 510 (Artificial Intelligence in Cloud Computing). The app ingests IT job postings,
classifies them with an owned ML model, compares keyword vs semantic retrieval, matches
resumes to jobs, and ships through a build → test → train → deploy pipeline to Azure.

## Documentation map

### Architecture
- [Overview](architecture/overview.md) — hexagonal layers, components, request flow
- [Data model](architecture/data-model.md) — entities, SQLite schema, model registry layout
- [Diagrams](architecture/diagrams.md) — end-to-end pipeline and per-feature flows

### Pipeline (features)
- [Data ingestion](pipeline/data-ingestion.md) — CSV / generic API / JSearch harvest, budget safety
- [Job search](pipeline/job-search.md) — keyword (TF-IDF) vs semantic (embedding) retrieval
- [Job matching](pipeline/job-matching.md) — resume PDF → cosine ranking → AI recommendations

### MLOps
- [Model card](mlops/model-card.md) — the job-role classifier, metrics, intended use, limits
- [Model usage](mlops/model-usage.md) — what the model is for and where it runs in the app
- [Training walkthrough](mlops/training-walkthrough.md) — how to train it, files produced, where they live, and which pages use them
- [Training pipeline](mlops/training-pipeline.md) — dataset, labels, training, versioning, registry
- [Lifecycle](mlops/lifecycle.md) — the ingest → retrain → build → deploy loop and drift detection

### Operations
- [Configuration](operations/configuration.md) — environment variables
- [CI/CD](operations/ci-cd.md) — the GitHub Actions build/test/train/deploy workflow
- [Deployment](operations/deployment.md) — local, Docker, and Azure Container Apps (quick map)
- [**Azure** (comprehensive)](operations/azure.md) — provision · deploy · run · scale · rollback · teardown
- [**Blue‑Green deploys**](operations/blue-green.md) — near‑zero‑downtime release strategy
- [**Azure monitoring**](operations/azure-monitoring.md) — inspect resources · logs · metrics · dashboards · live URL
- [Observability](operations/observability.md) — structured logging and offline evaluation
- [Runbooks](operations/runbooks/) — dated operational procedures

### Report (Team Project TP03)
- [Findings](report/findings.md) — methods, dataset, model results, MLOps & deployment findings
- [Slides](report/slides.md) — presentation deck (Marp/Markdown)

### Development
- [Getting started](development/getting-started.md) — install, run, first model
- [Project structure](development/project-structure.md) — directory map
- [Testing & verification](development/testing.md) — pytest suite and runtime verification

## Quick links

| What | Where |
|------|-------|
| Run the app | `streamlit run app.py` → http://localhost:8501 |
| Use the shared Azure DB locally | Set `DATABASE_URL` to the Azure PostgreSQL DSN first |
| Train the model | `python ml/train_role_classifier.py` |
| Harvest jobs | `python testing/scripts/harvest_jobs_jsearch.py --dry-run` |
| Run tests | `python -m pytest tests/ -q` |
| CI/CD workflow | [.github/workflows/ci-cd.yml](../.github/workflows/ci-cd.yml) |
| Deployment guide | [DEPLOYMENT.md](../DEPLOYMENT.md) |
