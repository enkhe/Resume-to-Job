# Runbook — Enable & Trigger the Azure Deploy

**Timestamp:** 2026-06-05 20:21 UTC
**Author:** Team 3 (with Claude)
**Purpose:** Set the GitHub Actions Variables/Secrets correctly, then commit this file to trigger the
CI/CD → blue‑green deploy and watch it land on Azure.

> Reference docs: [CI/CD](../ci-cd.md) · [Azure provision/deploy](../azure.md) ·
> [Blue‑Green](../blue-green.md) · [Inspect/Logs/Metrics](../azure-monitoring.md)

---

## 1. The deploy location (live URL)

**https://resume2job.agreeableisland-ffa9d6f6.eastus.azurecontainerapps.io/**

This is the Container App’s ingress FQDN. Re‑derive it any time:

```bash
az containerapp show -n resume2job -g rg-resume2job \
  --query properties.configuration.ingress.fqdn -o tsv
```

Portal: *Container App `resume2job` → Overview → “Application Url”.*
Status at time of writing: **Running**, HTTP `200` on `/_stcore/health`, image `:pg1`, revision
`resume2job--0000001` at 100% traffic. After this deploy a new `resume2job--g<sha>` revision appears.

---

## 2. GitHub configuration — exact values

*Settings → Secrets and variables → Actions.* **The tab is dictated by how the workflow references the
name (`vars.` vs `secrets.`), not by sensitivity** — e.g. `AZURE_ACR_USERNAME` is not secret but must
live under **Secrets** because the workflow reads `secrets.AZURE_ACR_USERNAME`.

### Variables tab (4) — plain values

| Name | Value |
|------|-------|
| `ENABLE_DEPLOY` | `true` |
| `AZURE_ACR_LOGIN_SERVER` | `r2jacr254b32a1.azurecr.io` |
| `AZURE_RESOURCE_GROUP` | `rg-resume2job` |
| `AZURE_CONTAINERAPP_NAME` | `resume2job` |

### Secrets tab (3)

| Name | Value / how to get it |
|------|-----------------------|
| `AZURE_ACR_USERNAME` | `r2jacr254b32a1` |
| `AZURE_ACR_PASSWORD` | `az acr credential show -n r2jacr254b32a1 --query "passwords[0].value" -o tsv` |
| `AZURE_CREDENTIALS` | full JSON from the `create-for-rbac` command below |

```bash
# AZURE_CREDENTIALS — paste the ENTIRE JSON object it prints into the secret
az ad sp create-for-rbac \
  --name sp-resume2job-gha \
  --role contributor \
  --scopes /subscriptions/254b32a1-bd19-4490-a908-d2ed56cd6ab1/resourceGroups/rg-resume2job \
  --sdk-auth
```

> `create-for-rbac` makes a **new** service principal each run. If you already have a working
> `AZURE_CREDENTIALS`, keep it. To rotate without recreating: `az ad sp credential reset --id <appId> --sdk-auth`.

---

## 3. Trigger the deploy

Two ways — either works now that the variables are set:

```bash
# A) Commit this runbook (any push to main triggers CI/CD)
git add .
git commit -m "docs: deploy-enablement runbook + Azure monitoring reference"
git push origin main
```

**B)** Or in the GitHub UI: *Actions → latest run → “Re‑run all jobs”* (re‑reads `ENABLE_DEPLOY`).

The `docker` and `Blue‑Green deploy` jobs run **only** on `main` **and** when `vars.ENABLE_DEPLOY ==
'true'`. If they show as *skipped* (0s), `ENABLE_DEPLOY` isn’t a **Variable** equal to `true`.

---

## 4. Watch the process

```bash
# Follow the GitHub Actions run end-to-end
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')

# Watch the blue-green swap on Azure (new green revision → 100%, blue → 0%)
watch -n 5 'az containerapp revision list -n resume2job -g rg-resume2job \
  --query "[].{rev:name, active:properties.active, traffic:properties.trafficWeight, state:properties.runningState}" -o table'

# Confirm the site serves after the swap
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  https://resume2job.agreeableisland-ffa9d6f6.eastus.azurecontainerapps.io/_stcore/health
```

Portal live view: *Container App → Monitoring → Log stream* and *→ Metrics*. Full command/portal
catalog (resources, logs, KQL queries, metrics, dashboards) is in
[azure-monitoring.md](../azure-monitoring.md).

---

## 5. Expected outcome

1. CI: `build-test-train` ✅ → `docker` builds & pushes `resume-to-job:<sha>` to ACR.
2. `Blue-Green deploy`: green revision `resume2job--g<sha7>` comes up at 0% → health check passes →
   traffic shifts to 100% green, blue retained at 0%.
3. The live URL serves the new build with **near‑zero downtime**.
4. Rollback (if needed): flip traffic back to the previous revision (seconds, no rebuild).
