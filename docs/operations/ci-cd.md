# CI/CD

The pipeline is defined in [.github/workflows/ci-cd.yml](../../.github/workflows/ci-cd.yml).

## Triggers
- `push` to `main`, `pull_request` to `main`, and manual `workflow_dispatch`.

## Jobs

### 1. `build-test-train` (always)
1. Checkout, set up Python 3.11 (pip cache).
2. `pip install -r requirements.txt -r requirements-dev.txt`.
3. `python -m pytest tests/ -q` — the [unit suite](../development/testing.md).
4. **Train the model**: `python ml/train_role_classifier.py` (skipped with a warning if the
   harvested dataset isn't committed).
5. Upload `models/` as the `model-artifact`.

This is the MLOps core: every change re-runs tests and **re-produces the model from data**.

### 2. `docker` (gated)
Runs only on `main`/dispatch **and** when repo variable `ENABLE_DEPLOY == 'true'`.
Downloads the trained model artifact, builds the image, and pushes to Azure Container Registry.

### 3. `deploy` (gated) — blue‑green
Same gate, `environment: production`. Performs a **blue‑green** release on Azure Container Apps: rolls
out the new image as a **green** revision at 0% traffic, health‑checks it on its own FQDN, then
shifts 100% of traffic to it (keeping the previous **blue** revision warm for instant rollback). Full
mechanics in [Blue‑Green deploys](blue-green.md).

## Required GitHub configuration

| Kind | Name | Purpose |
|------|------|---------|
| Variable | `ENABLE_DEPLOY` | `true` enables the docker + deploy jobs. |
| Variable | `AZURE_ACR_LOGIN_SERVER` | e.g. `myregistry.azurecr.io` |
| Variable | `AZURE_RESOURCE_GROUP` | Container App resource group. |
| Variable | `AZURE_CONTAINERAPP_NAME` | Target Container App name. |
| Secret | `AZURE_CREDENTIALS` | `az ad sp create-for-rbac --sdk-auth` output. |
| Secret | `AZURE_ACR_USERNAME` / `AZURE_ACR_PASSWORD` | ACR push credentials. |

> **Variables vs Secrets is load‑bearing.** The four non‑sensitive names go on the **Variables** tab;
> the three credentials go on the **Secrets** tab (*Settings → Secrets and variables → Actions*).
> Putting `AZURE_CREDENTIALS` or `AZURE_ACR_PASSWORD` under Variables makes the deploy fail to
> authenticate. See [Azure §6](azure.md#6-github-configuration--variables-vs-secrets-get-this-right).

## Design notes
- PRs and forks run **build-test-train only** — they never attempt a cloud deploy (no secrets
  needed) because of the `ENABLE_DEPLOY` gate.
- The model is trained in CI and **baked into the image**, so the deployed container serves the
  exact model that CI validated.
- See [deployment](deployment.md) for the one-time Azure setup the variables/secrets refer to.
