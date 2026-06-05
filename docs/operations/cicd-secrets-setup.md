# CI/CD Secrets & Variables Setup (GitHub → Azure)

How to configure the GitHub repository so the pipeline in
[.github/workflows/ci-cd.yml](../../.github/workflows/ci-cd.yml) can build the image, push it to
Azure Container Registry (ACR), and deploy to Azure Container Apps.

> **Security note:** the real secret *values* are **never** stored in this repository. The
> commands below *retrieve* them at run time so you can paste them straight into GitHub's
> encrypted secret store. Only the command recipes and non-sensitive resource names live here.

---

Set these once in your shell to make the commands below copy-paste-able:

```bash
az login                                   # if not already logged in
SUB=$(az account show --query id -o tsv)
RG=rg-resume2job
ACR=r2jacr254b32a1
APP=resume2job
SP_NAME=sp-resume2job-gha
```

## 1. Which of the four "kinds" do I use? → **Actions**

GitHub groups encrypted secrets/variables by the system that consumes them:

| Tab | Consumed by | Use it here? |
|-----|-------------|--------------|
| **Actions** | GitHub Actions workflow runs (`${{ secrets.X }}`, `${{ vars.X }}`) | ✅ **Yes — all of them go here** |
| **Codespaces** | Dev containers when you open a Codespace | ❌ No |
| **Dependabot** | Dependabot's dependency-update PR builds | ❌ No |
| **Agents** / Copilot | GitHub Copilot coding agent sessions | ❌ No |

Our pipeline runs in **GitHub Actions**, so every value below is created under the **Actions**
tab. Within it: **Secrets** (encrypted, masked — for credentials) and **Variables** (plain
text — for names/flags).

---

## 2. This project's resource identifiers

| Setting | Value |
|---------|-------|
| Subscription | `echo $SUB` (Visual Studio Enterprise) |
| Resource group | `rg-resume2job` |
| Container Registry | `r2jacr254b32a1` → login server `r2jacr254b32a1.azurecr.io` |
| Container App | `resume2job` (env `cae-resume2job`, region eastus) |
| Service principal | `sp-resume2job-gha` (appId `1a7dd81e-bdbc-49ac-b704-d8ce1c443f80`, scoped to the RG) |
| Postgres | `r2j-pg-254b32a1.postgres.database.azure.com` / db `jobs` (region centralus) |


---

## 3. Commands to obtain each value

### 🔐 Secrets (Actions → Secrets)

**`AZURE_CREDENTIALS`** — full SDK-auth JSON the `azure/login` action expects. This recipe
creates (or refreshes) the RG-scoped service principal and prints the JSON to paste:

```bash
az ad sp create-for-rbac \
  --name "$SP_NAME" \
  --role contributor \
  --scopes "/subscriptions/$SUB/resourceGroups/$RG" \
  --sdk-auth
# Paste the ENTIRE JSON object as the secret value.
# (--sdk-auth is deprecated but still the format azure/login@v2 `creds:` needs.
#  Re-running adds a new password to the same app — rotate/clean up old ones as needed.)
```

**`AZURE_ACR_USERNAME`**
```bash
az acr credential show -n "$ACR" --query username -o tsv
```

**`AZURE_ACR_PASSWORD`**
```bash
az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv
```

### ⚙️ Variables (Actions → Variables)

**`AZURE_ACR_LOGIN_SERVER`**
```bash
az acr show -n "$ACR" --query loginServer -o tsv          # -> r2jacr254b32a1.azurecr.io
```

**`AZURE_RESOURCE_GROUP`**
```bash
echo "$RG"                                                # -> rg-resume2job
```

**`AZURE_CONTAINERAPP_NAME`**
```bash
echo "$APP"                                               # -> resume2job
```

**`ENABLE_DEPLOY`** — literal master switch (the docker + deploy jobs are skipped unless this is `true`):
```text
true
```

---

## 4. Two ways to set them

### A. GitHub web UI (most secure — values never touch a shell)

Repo → **Settings** → **Secrets and variables** → **Actions** →
**Secrets** sub-tab (the 3 secrets) and **Variables** sub-tab (the 4 variables).
For `AZURE_CREDENTIALS`, paste the full JSON block as the value.

### B. GitHub CLI (`gh`) — pipe each command straight into the secret

Requires a login with the `repo` scope (the Codespaces `GITHUB_TOKEN` does **not** have it —
you'll get `HTTP 403: Resource not accessible by integration`). `gh auth login` with a PAT first.

```bash
REPO=enkhe/r2j

# Secrets — value piped from the az command via stdin (never in shell history)
az ad sp create-for-rbac --name "$SP_NAME" --role contributor \
  --scopes "/subscriptions/$SUB/resourceGroups/$RG" --sdk-auth \
  | gh secret set AZURE_CREDENTIALS --repo "$REPO"

az acr credential show -n "$ACR" --query username -o tsv \
  | gh secret set AZURE_ACR_USERNAME --repo "$REPO"

az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv \
  | gh secret set AZURE_ACR_PASSWORD --repo "$REPO"

# Variables
gh variable set ENABLE_DEPLOY           --repo "$REPO" --body 'true'
gh variable set AZURE_ACR_LOGIN_SERVER  --repo "$REPO" --body "$(az acr show -n "$ACR" --query loginServer -o tsv)"
gh variable set AZURE_RESOURCE_GROUP    --repo "$REPO" --body "$RG"
gh variable set AZURE_CONTAINERAPP_NAME --repo "$REPO" --body "$APP"
```

---

## 5. Verify & trigger

```bash
gh secret list   --repo "$REPO"
gh variable list --repo "$REPO"
gh workflow run 'CI/CD' --repo "$REPO" --ref main   # manual trigger (workflow_dispatch)
gh run watch --repo "$REPO"
```

Or in the UI: **Actions** → **CI/CD** → **Run workflow** → `main`. With `ENABLE_DEPLOY=true`
the `docker` + `deploy` jobs now run instead of skipping. The first deploy auto-creates a
**`production`** environment — add required reviewers there later for a manual approval gate.

---

## 6. Security best practices

- **Least privilege:** the SP is scoped to the resource group, not the whole subscription.
- **Rotate after sharing** (if a value was ever shown in a chat/terminal):
  ```bash
  az ad sp credential reset --id 1a7dd81e-bdbc-49ac-b704-d8ce1c443f80   # -> update AZURE_CREDENTIALS
  az acr credential renew  -n "$ACR" --password-name password           # -> update AZURE_ACR_PASSWORD
  ```
- **Prefer OIDC (no stored password)** for a hardened setup: federate the SP with GitHub via
  `azure/login` OIDC and drop `AZURE_CREDENTIALS`. (Future enhancement.)
- `DATABASE_URL` is **not** a GitHub secret — it lives as a Container App secret and survives
  image-only `az containerapp update`, so the pipeline never needs the DB password.
