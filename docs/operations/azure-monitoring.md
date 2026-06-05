# Azure — Inspect, Logs, Metrics & Dashboards

How to see **what you have**, the **live deploy URL**, **logs**, **metrics**, and **status** for
Resume‑to‑Job — both from the **Azure CLI** and the **Azure Portal**. Companion to
[azure.md](azure.md) (provision/deploy) and [blue-green.md](blue-green.md) (releases).

Quick constants for this deployment:

| Thing | Value |
|-------|-------|
| Subscription | `254b32a1-bd19-4490-a908-d2ed56cd6ab1` (Visual Studio Enterprise) |
| Resource group | `rg-resume2job` |
| Container App | `resume2job` |
| **Live URL** | **https://resume2job.agreeableisland-ffa9d6f6.eastus.azurecontainerapps.io/** |
| Container Apps env | `cae-resume2job` (eastus) |
| Registry | `r2jacr254b32a1.azurecr.io` |
| PostgreSQL | `r2j-pg-254b32a1.postgres.database.azure.com` (centralus, db `jobs`) |

---

## 1. The live deploy URL — where it comes from

The public URL is the Container App’s **ingress FQDN**. Get it any time:

```bash
az containerapp show -n resume2job -g rg-resume2job \
  --query properties.configuration.ingress.fqdn -o tsv
# -> resume2job.agreeableisland-ffa9d6f6.eastus.azurecontainerapps.io
```

Prefix with `https://` → that’s the site. The CI/CD run’s **Release summary** also prints the image
and result, and each blue‑green revision has its **own** URL:

```bash
# Per-revision FQDN (used for private health checks during blue-green)
az containerapp revision list -n resume2job -g rg-resume2job \
  --query "[].{revision:name, fqdn:properties.fqdn, active:properties.active, traffic:properties.trafficWeight}" -o table
```

In the **Portal**: *Container App → Overview → “Application Url”* (top‑right).

---

## 2. See everything you have (inventory)

```bash
# Everything in the resource group
az resource list -g rg-resume2job -o table

# By type
az containerapp list -g rg-resume2job -o table
az acr list -g rg-resume2job -o table
az postgres flexible-server list -g rg-resume2job -o table
az containerapp env list -g rg-resume2job -o table

# All resource groups in the subscription
az group list -o table

# Costs / what's billing (needs cost-management ext)
az consumption usage list --top 20 -o table 2>/dev/null || echo "enable Cost Management in the Portal"
```

**Portal:** *Resource groups → `rg-resume2job`* shows the whole stack. Direct link:
`https://portal.azure.com/#@/resource/subscriptions/254b32a1-bd19-4490-a908-d2ed56cd6ab1/resourceGroups/rg-resume2job/overview`

---

## 3. App status & health

```bash
# One-shot status (provisioning + running + active revision + image)
az containerapp show -n resume2job -g rg-resume2job \
  --query "{state:properties.provisioningState, running:properties.runningStatus, rev:properties.latestRevisionName, image:properties.template.containers[0].image}" -o json

# Revisions + their traffic weights (blue/green at a glance)
az containerapp revision list -n resume2job -g rg-resume2job -o table
az containerapp ingress traffic show -n resume2job -g rg-resume2job -o table

# Running replicas (the live containers)
az containerapp replica list -n resume2job -g rg-resume2job -o table

# App-level health probe (200 = healthy)
curl -s -o /dev/null -w "%{http_code}\n" \
  https://resume2job.agreeableisland-ffa9d6f6.eastus.azurecontainerapps.io/_stcore/health
```

---

## 4. Logs

The app writes **structured JSON line logs** (ingest / match / AI use cases). Two streams:

```bash
# Application logs (your app's stdout/stderr) — live tail
az containerapp logs show -n resume2job -g rg-resume2job --follow --tail 100

# A specific revision/replica
az containerapp logs show -n resume2job -g rg-resume2job \
  --revision <revision-name> --follow

# System/platform logs (scaling, image pulls, probe failures, restarts)
az containerapp logs show -n resume2job -g rg-resume2job --type system --follow
```

**Portal — live:** *Container App → Monitoring → **Log stream*** (real‑time console).

**Portal — query history (Log Analytics / KQL):** *Container App → Monitoring → **Logs***, then query
the Container Apps tables:

```kusto
// Last 1h of app console logs
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "resume2job"
| order by _timestamp_d desc
| take 200

// System events (scaling, restarts, probe failures)
ContainerAppSystemLogs_CL
| where ContainerAppName_s == "resume2job"
| order by _timestamp_d desc
| take 200

// Error lines only
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "resume2job" and Log_s has "error"
| order by _timestamp_d desc
```

Find the workspace backing the environment:

```bash
az containerapp env show -n cae-resume2job -g rg-resume2job \
  --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId -o tsv
```

---

## 5. Metrics (CPU, memory, requests, replicas)

```bash
# What metrics are available
az monitor metrics list-definitions \
  --resource $(az containerapp show -n resume2job -g rg-resume2job --query id -o tsv) \
  --query "[].name.value" -o tsv

# Example: requests + CPU + memory over the last hour (5-min buckets)
APP_ID=$(az containerapp show -n resume2job -g rg-resume2job --query id -o tsv)
az monitor metrics list --resource "$APP_ID" \
  --metric Requests UsageNanoCores WorkingSetBytes Replicas \
  --interval PT5M --output table
```

Useful Container Apps metric names: `Requests`, `UsageNanoCores` (CPU), `WorkingSetBytes` (memory),
`Replicas`, `RxBytes`/`TxBytes` (network), `RestartCount`.

**Portal — charts:** *Container App → Monitoring → **Metrics*** → pick a metric (e.g. *Requests*),
split by *Revision* to compare blue vs green. Pin charts to a dashboard (next section).

Postgres metrics: *PostgreSQL flexible server → Monitoring → Metrics* (`cpu_percent`,
`memory_percent`, `active_connections`, `storage_percent`).

---

## 6. Dashboard view of the deployed site

You have several “single pane of glass” options:

1. **Container App → Overview** — the fastest live view: status, Application Url, a built‑in
   CPU/memory/requests/replica mini‑dashboard, and revision list.
2. **Azure Dashboard (custom):** *Portal → Dashboard → New dashboard*, then **pin** tiles from the
   app’s *Metrics* and *Log stream* blades (Requests, CPU, Memory, Replicas, error‑log query).
   Share it with the team via *Share → publish to the resource group*.
3. **Azure Monitor → Workbooks:** *Container App → Monitoring → Workbooks* has prebuilt Container
   Apps workbooks (traffic, performance, failures) — good for the report screenshots.
4. **Application Map / Insights (optional upgrade):** enabling Application Insights adds
   request traces and a live metrics stream; not enabled by default here.

Direct portal links (this deployment):

```text
Container App overview:
https://portal.azure.com/#@/resource/subscriptions/254b32a1-bd19-4490-a908-d2ed56cd6ab1/resourceGroups/rg-resume2job/providers/Microsoft.App/containerApps/resume2job/overview

Container App metrics:
…/providers/Microsoft.App/containerApps/resume2job/metrics

Container App log stream:
…/providers/Microsoft.App/containerApps/resume2job/logstream
```

---

## 7. Watch a deployment happen (CI/CD + blue-green)

```bash
# From the repo: follow the GitHub Actions run
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')

# From Azure: watch the new green revision appear and take traffic
watch -n 5 'az containerapp revision list -n resume2job -g rg-resume2job \
  --query "[].{rev:name, active:properties.active, traffic:properties.trafficWeight, state:properties.runningState}" -o table'
```

During a blue‑green release you’ll see a new `resume2job--g<sha7>` revision come up at **0%**, then
flip to **100%** while the old one drops to **0%** (kept warm for rollback).

---

## 8. Quick reference card

| I want to… | Command |
|------------|---------|
| Get the site URL | `az containerapp show -n resume2job -g rg-resume2job --query properties.configuration.ingress.fqdn -o tsv` |
| See all my resources | `az resource list -g rg-resume2job -o table` |
| Tail app logs | `az containerapp logs show -n resume2job -g rg-resume2job --follow` |
| See CPU/mem/requests | `az monitor metrics list --resource <appId> --metric Requests UsageNanoCores WorkingSetBytes -o table` |
| Check who serves traffic | `az containerapp ingress traffic show -n resume2job -g rg-resume2job -o table` |
| Health check | `curl …/_stcore/health` |
| Roll back | `az containerapp ingress traffic set … --revision-weight <prev>=100 <cur>=0` |
