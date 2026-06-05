# Deployment & MLOps

Resume-to-Job ships as a single container and follows a build → test → **train model** →
package → **blue‑green deploy** pipeline. The model artifact
(`models/job_role_classifier/<version>/model.joblib`) is produced by CI, baked into the image, and
served by the app.

> **This page is the quick‑start.** For the full Azure guide (provision, run, scale, rollback,
> teardown, troubleshooting) see [docs/operations/azure.md](docs/operations/azure.md); for the
> near‑zero‑downtime release strategy see [docs/operations/blue-green.md](docs/operations/blue-green.md);
> for the Team Project write‑up see [docs/report/findings.md](docs/report/findings.md) and
> [docs/report/slides.md](docs/report/slides.md).

## 1. Run locally

```bash
pip install -r requirements.txt
python ml/train_role_classifier.py      # produce models/job_role_classifier/vN
streamlit run app.py                     # http://localhost:8501
```

## 2. Run as a container

```bash
docker compose up --build
# or
docker build -t resume-to-job:latest .
docker run -p 8501:8501 -v "$PWD/data:/app/data" resume-to-job:latest
```

The image pre-downloads the embedding model and copies in the trained classifier, so it
runs without network access to Hugging Face at runtime.

## 2b. Shared database (local + cloud)

The container filesystem on Azure Container Apps is **ephemeral** — anything written to a
local SQLite file is lost on restart/redeploy. So jobs and their embeddings are persisted in
a **shared Azure Database for PostgreSQL** that both the local app and the cloud app connect to.

Selection is environment-driven (see `src/adapters/outbound/persistence/repository_factory.py`):

| `DATABASE_URL` | Store used |
|----------------|------------|
| set | **PostgreSQL** — shared, persistent (jobs + embeddings) |
| unset | **SQLite** at `JOB_DB_PATH` (offline / no-network dev) |

```bash
# Point local dev at the same Postgres the cloud uses:
export DATABASE_URL='postgresql://r2jadmin:<pass>@<server>.postgres.database.azure.com:5432/jobs?sslmode=require'
streamlit run app.py

# One-time migrate an existing local SQLite catalog into Postgres:
DATABASE_URL="$DATABASE_URL" JOB_DB_PATH=data/jobs.db \
  python testing/scripts/migrate_sqlite_to_postgres.py
```

`sslmode=require` is appended automatically if omitted (Azure requires TLS). The same
`DATABASE_URL` is set as a secret env var on the Container App, so ingesting jobs in the cloud
persists them for everyone.

## 3. MLOps loop (why CI/CD exists)

```
ingest new jobs  ->  retrain  ->  new model version (model.joblib)  ->  build image  ->  deploy
   (JSearch)       (ml/train_*)     (registry.json bumps "latest")     (CI)            (Azure)
```

Ingesting new postings changes the dataset fingerprint, which the **Model Ops** page flags.
Retraining registers a new version — that new artifact is the trigger for the automated
build/release pipeline in [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml).

## 4. CI/CD (GitHub Actions)

`.github/workflows/ci-cd.yml` runs:

1. **build-test-train** — install deps, `pytest`, then `python ml/train_role_classifier.py`
   (re-produces the model from the committed dataset) and uploads the model as a build artifact.
   Runs on every push and PR.
2. **docker** — downloads the trained model, builds the image, pushes to Azure Container Registry.
3. **deploy** — deploys the image to Azure.

Jobs 2–3 only run on `main` (or manual dispatch) **and** when the repo variable
`ENABLE_DEPLOY=true`, so forks/PRs never attempt a cloud deploy.

### Required GitHub configuration

| Type | Name | Purpose |
|------|------|---------|
| Variable | `ENABLE_DEPLOY` | Set to `true` to enable the docker + deploy jobs. |
| Variable | `AZURE_ACR_LOGIN_SERVER` | e.g. `myregistry.azurecr.io` |
| Variable | `AZURE_RESOURCE_GROUP` | Resource group of the Container App. |
| Variable | `AZURE_CONTAINERAPP_NAME` | Target Azure Container App name. |
| Secret | `AZURE_CREDENTIALS` | Output of `az ad sp create-for-rbac --sdk-auth`. |
| Secret | `AZURE_ACR_USERNAME` / `AZURE_ACR_PASSWORD` | ACR push credentials. |

### One-time Azure setup (Container Apps)

```bash
az group create -n rg-resume2job -l eastus
az acr create -n <registry> -g rg-resume2job --sku Basic --admin-enabled true
az containerapp env create -n cae-resume2job -g rg-resume2job -l eastus
az containerapp create -n resume2job -g rg-resume2job \
  --environment cae-resume2job \
  --image <registry>.azurecr.io/resume-to-job:latest \
  --target-port 8501 --ingress external \
  --registry-server <registry>.azurecr.io
```

> Note: training in CI requires the harvested dataset (`data/jsearch_raw/` + `manifest.json`)
> to be committed. If it is absent, CI skips retraining and ships the committed model.
