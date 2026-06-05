# Deployment

This page is a quick map of the deploy targets. For the **comprehensive, reproducible Azure guide**
(provision → deploy → run → scale → rollback → teardown, with real resource names) see
[**Azure**](azure.md); for the release strategy see [**Blue‑Green deploys**](blue-green.md). The root
[DEPLOYMENT.md](../../DEPLOYMENT.md) is the condensed quick‑start.

## Targets

| Target | How | Notes |
|--------|-----|-------|
| Local | `streamlit run app.py` | Dev loop; port 8501. |
| Docker | `docker compose up --build` | Reproducible; mounts `./data`. |
| Azure Container Apps | CI `deploy` job / `az containerapp` | Production target for TP03. |

## Container image
[Dockerfile](../../Dockerfile) — Python 3.11-slim. It:
- installs `requirements.txt`,
- **pre-downloads** `all-MiniLM-L6-v2` so runtime needs no Hugging Face network,
- copies the repo (including `models/` so the trained classifier ships in the image),
- exposes 8501 with a `/_stcore/health` healthcheck.

`data/jobs.db` is excluded from the image ([.dockerignore](../../.dockerignore)) and provided as a
runtime volume so the catalog persists across restarts.

## Azure (Container Apps) — one-time setup
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
Then set the GitHub Variables/Secrets from [CI/CD](ci-cd.md) and push to `main` with
`ENABLE_DEPLOY=true`.

## Runtime configuration
Provide the same environment variables as local — see [configuration](configuration.md). At minimum
set an LLM key (`AI_API_KEY`/`GEMINI_API_KEY`) for the AI recommendations feature; everything else
works offline.
