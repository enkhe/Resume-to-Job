# Resume‑to‑Job: An MLOps Job‑Search Platform on Azure — Findings

**Course:** AI 510 — Artificial Intelligence in Cloud Computing · **Team Project TP03** · Team 3
**Authors:** Ruojie · Akzhol · Duy · Quan · Enkhamgalan
**Artifact:** `resume-to-job` v2.0 — Streamlit app, owned ML model, CI/CD to Azure Container Apps
**Live URL:** `https://resume2job.agreeableisland-ffa9d6f6.eastus.azurecontainerapps.io/`

> This document collects the engineering and empirical findings to fold into the team research paper
> and slide deck. It is grounded in the committed artifacts: model metrics
> (`models/job_role_classifier/v2/metrics.json`), the harvested dataset, the
> [CI/CD workflow](../../.github/workflows/ci-cd.yml), and the Azure deployment.

---

## 1. Abstract

We built an end‑to‑end, cloud‑native **MLOps** application that ingests IT job postings, classifies
them with an **owned, retrainable** model, contrasts keyword vs semantic retrieval, ranks postings
against a resume, and optionally produces LLM recommendations. The system is packaged as a single
container and shipped through a **build → test → train → package → blue‑green deploy** pipeline to
**Azure Container Apps**, backed by a shared **PostgreSQL** store. The role classifier
(TF‑IDF + Logistic Regression over 1,129 labeled postings, 11 categories) reaches **88.9% accuracy /
0.877 macro‑F1** on a held‑out split with **0.836 ± 0.023** 5‑fold CV macro‑F1. The contribution is
not the model alone but the **reproducible lifecycle** around it: data changes regenerate the
dataset and trigger retraining, CI validates and bakes the model into the image, and blue‑green
releases achieve **near‑zero‑downtime** deployments with instant rollback.

---

## 2. Problem & objectives

Job seekers face two costs: (1) **finding** relevant postings in high‑volume, noisily‑labeled feeds,
and (2) **judging fit** against their own experience. Course objectives required an AI system that is
not just a notebook but a **deployed, operable, continuously improvable cloud service**.

Objectives:
1. Ingest real job data from multiple sources at controlled cost.
2. Train and **own** an ML model (not just call a hosted API) with a reproducible pipeline.
3. Demonstrate the difference between **keyword** and **semantic** retrieval.
4. Provide resume‑to‑job matching and AI recommendations.
5. Operate it as a **cloud service** with CI/CD, observability, and low‑downtime releases.

---

## 3. System architecture (findings)

The app uses a **hexagonal (ports & adapters)** design. Business logic depends only on ports;
infrastructure (SQLite/Postgres, Sentence‑Transformers, scikit‑learn, LLM, Streamlit) lives in
swappable adapters. **Finding:** this paid off concretely — we swapped the persistence adapter from
**SQLite → PostgreSQL** with *no change to use cases or domain code*, driven entirely by a
`repository_factory` that reads `DATABASE_URL`. See
[architecture overview](../architecture/overview.md) and [diagrams](../architecture/diagrams.md).

| Concern | Port | Adapter |
|---------|------|---------|
| Persistence | `JobRepositoryPort` | `SQLiteJobRepository` / `PostgresJobRepository` |
| Embeddings | `EmbeddingServicePort` | `all-MiniLM-L6-v2` (384‑dim) |
| Role classification | `JobClassifierPort` | TF‑IDF + LogisticRegression |
| AI recommendations | `ResumeRecommendationServicePort` | OpenAI‑compatible (Gemini) |
| Keyword search | — | TF‑IDF cosine |

**Key design finding — the ephemeral filesystem.** Container Apps’ filesystem is **ephemeral**;
SQLite‑in‑image data was wiped on every restart/redeploy. Moving jobs + embeddings to a **shared
Postgres** server (reachable by both local dev and the cloud app) was necessary for the catalog to
survive deploys *and* let blue/green revisions share one source of truth.

---

## 4. Dataset (findings)

- **Source:** JSearch (RapidAPI) IT postings, harvested over a query matrix of roles × US locations.
- **Size:** **1,129** unique jobs after dedup by `job_id`.
- **Labels for free (weak supervision):** each posting is labeled with the **canonical category of
  the role query that surfaced it**, recorded in `data/jsearch_raw/manifest.json` (majority vote when
  multiple queries return the same job). This converts a search log into a labeled dataset at zero
  annotation cost.
- **Classes (11):** Software Engineering, Frontend, Backend, Full Stack, Data & Analytics,
  Machine Learning / AI, Cloud & DevOps, Cybersecurity, IT Infrastructure & Support, QA & Testing,
  Mobile.
- **Reproducibility:** the raw responses are cached on disk and re‑ingestible **for free**; the
  dataset carries a `data_fingerprint` (hash of ids+labels) so the app can detect drift between the
  corpus and the trained model.

**Budget‑safety finding:** the harvester checks the manifest *before* every request and writes raw
JSON to disk *before* updating state, so a re‑run spends **no** API quota on already‑fetched
(query, page) pairs — important under JSearch’s ~200‑requests/month free tier.

---

## 5. Model results

**Model:** scikit‑learn `Pipeline` = `TfidfVectorizer` (1–2 grams, English stop‑words, sublinear TF)
→ `LogisticRegression` (`class_weight="balanced"`, `C=2.0`). Train/test = 903 / 226 (stratified
80/20, `random_state=42`).

### Headline metrics (held‑out test split, v2)

| Metric | Value |
|--------|-------|
| Accuracy | **0.889** |
| F1 (macro) | **0.877** |
| F1 (weighted) | 0.889 |
| CV F1‑macro (5‑fold) | **0.836 ± 0.023** |

The gap between test macro‑F1 (0.877) and CV macro‑F1 (0.836) is small and within CV variance —
**finding: the model is not materially overfit** to the single test split.

### Per‑class F1 (test split)

| Class | Precision | Recall | F1 | Support |
|-------|-----------|--------|----|---------|
| Cybersecurity | 1.00 | 0.94 | **0.968** | 16 |
| IT Infrastructure & Support | 0.96 | 0.98 | **0.970** | 49 |
| QA & Testing | 0.83 | 1.00 | 0.909 | 10 |
| Mobile | 0.89 | 0.89 | 0.889 | 9 |
| Frontend | 0.85 | 0.92 | 0.880 | 12 |
| Data & Analytics | 0.88 | 0.84 | 0.864 | 45 |
| Software Engineering | 0.84 | 0.87 | 0.857 | 31 |
| Full Stack | 1.00 | 0.75 | 0.857 | 12 |
| Cloud & DevOps | 0.89 | 0.80 | 0.842 | 20 |
| Machine Learning / AI | 0.77 | 0.91 | 0.833 | 11 |
| Backend | 0.75 | 0.82 | 0.783 | 11 |

**Findings from the per‑class breakdown:**
- **Best separated:** *Cybersecurity* and *IT Infrastructure & Support* — distinct, low‑ambiguity
  vocabulary (e.g. “SOC”, “SIEM”, “help desk”, “Active Directory”).
- **Hardest:** *Backend* (0.78) and *ML/AI* (0.83) — they share tokens with adjacent classes
  (*Full Stack*, *Software Engineering*, *Data & Analytics*). This is expected: a posting can be
  genuinely cross‑category, which caps separability between neighbours.
- **Recall‑favoured by design:** `class_weight="balanced"` lifts recall on small classes
  (QA 1.00, ML/AI 0.91) at a modest precision cost — appropriate for a *tagging* aid rather than a
  gating decision.

**Why this model (finding on model choice):** TF‑IDF + LogisticRegression is **interpretable,
fast to train (seconds), CPU‑only, and tiny to ship** (a `model.joblib` baked into the image). For a
weakly‑labeled tagging task that must retrain in CI on every data change, this beats a heavyweight
transformer fine‑tune on cost/latency/operability for equal‑or‑better practical accuracy.

---

## 6. Retrieval finding: keyword vs semantic

Running the same query through **TF‑IDF (lexical)** and **MiniLM embeddings (semantic)** and taking
the set difference shows **semantic‑only** hits: postings that match intent without sharing surface
tokens (e.g. a query “ML engineer” surfacing a “Applied Scientist, recommendations” posting that
keyword search misses). **Finding:** semantic retrieval improves recall on paraphrase/synonymy;
keyword retrieval remains stronger for exact‑term, acronym‑heavy queries. Exposing both side‑by‑side
in the **Job Search** page is itself a teaching artifact about embedding behaviour.

---

## 7. MLOps & CI/CD findings

The pipeline ([.github/workflows/ci-cd.yml](../../.github/workflows/ci-cd.yml)) runs on every push:

1. **build‑test‑train** (always): `pytest`, then `python ml/train_role_classifier.py` —
   **the model is re‑produced from data in CI**, not committed blindly. Uploaded as an artifact.
2. **docker** (gated on `main` + `ENABLE_DEPLOY=true`): build image, push to ACR.
3. **deploy** (same gate): **blue‑green** release to Container Apps.

**Findings:**
- **Data change *is* the build trigger.** Ingesting postings changes the dataset fingerprint; the
  Model Ops page flags drift; retraining registers a new immutable version; pushing triggers the
  pipeline. The MLOps loop is closed and automated, not manual.
- **Train‑in‑CI guarantees parity.** The container serves the *exact* model CI validated, because
  the artifact is baked into the image — no “works in the notebook, not in prod” gap.
- **Gating keeps forks/PRs safe.** PRs run build‑test‑train only; no secrets, no cloud calls.
- **Tooling constraint discovered:** an Actions/Codespaces `GITHUB_TOKEN` **cannot** write Actions
  secrets/variables or trigger `workflow_dispatch` (HTTP 403). Secrets must be set via the GitHub UI
  or a PAT; a push to `main` is the reliable deploy trigger.
- **Variables vs Secrets split is load‑bearing.** Non‑sensitive config (`ENABLE_DEPLOY`,
  registry/app/RG names) are repo **Variables**; credentials (`AZURE_CREDENTIALS`, ACR user/pass)
  are **Secrets**. Misplacing one silently skips or fails the deploy — documented as the top
  operational gotcha.

---

## 8. Deployment finding: blue‑green near‑zero downtime

We replaced an in‑place `az containerapp update` (which briefly serves a cold/half‑started
container) with a **blue‑green** release on Container Apps revisions:

1. Switch to **multiple‑revision** mode.
2. Roll out the new image as **GREEN at 0% traffic** (deterministic `--revision-suffix g<sha7>`).
3. **Health‑check GREEN privately** on its own revision FQDN (`/_stcore/health`) — the model and
   embeddings must load and answer a real probe **before** any user is routed to it.
4. **Shift 100% traffic** BLUE → GREEN only on a `200`.
5. On failure, **deactivate GREEN**; BLUE never lost traffic → the bad release is invisible.
6. Keep BLUE warm → **rollback is a seconds‑long traffic flip**, no rebuild.

**Finding:** the per‑revision health gate is what makes downtime *near‑zero* rather than just
*shorter* — the swap is conditioned on the new container already being warm. The same primitive
generalizes to **canary** (weighted 90/10 → 50/50 → 0/100) for progressive delivery.

**One rule for the future:** because BLUE and GREEN share one Postgres, schema changes must be
**backward compatible** (expand‑then‑contract) during the overlap window. The current `jobs` schema
is stable, so this is not a present concern.

---

## 9. Observability findings

- **Runtime:** use cases emit **structured JSON line logs** (ingest, match, AI) tailable via
  `az containerapp logs show --follow`. Platform events (scaling, image pulls, probe failures) go to
  Log Analytics.
- **Offline:** `testing/scripts/pipeline_eval.py` reproduces match/AI quality on fixtures for
  regression checks independent of the UI.

---

## 10. Limitations

- **Weak labels.** Categories come from search queries, not human annotation; genuinely
  cross‑category postings cap separability between adjacent classes.
- **Lexical model.** TF‑IDF generalizes to seen vocabulary, not unseen jargon; an embedding‑based
  classifier is a natural upgrade.
- **Single harvest window, US IT only** — not representative of other markets/eras.
- **No metrics‑gated promotion yet** — a regressing model can still be promoted (mitigated by
  retained versions + easy rollback).
- **Cosine similarity computed in Python**, not in the DB — fine at this scale; **pgvector** is the
  scaling path.

---

## 11. Future work

1. **Promotion gate** in CI: refuse to deploy if held‑out macro‑F1 regresses beyond a threshold;
   champion/challenger comparison.
2. **Embedding classifier** (MiniLM features → linear head) to lift Backend/ML‑AI separability.
3. **pgvector** for in‑database ANN search as the catalog grows.
4. **MLflow** experiment tracking/registry; **scheduled retrain** after each harvest.
5. **Canary automation** gated on Log‑Analytics error‑rate before ramping traffic.
6. **Managed identity** for ACR/Postgres instead of admin credentials.

---

## 12. Conclusion

The deliverable is a **working, observable, continuously‑deployed cloud service**, not a notebook.
The owned classifier performs well (0.889 acc / 0.877 macro‑F1) for an interpretable, CPU‑only model
trained on free weak labels, and — more importantly for the course outcomes — it lives inside a
**closed MLOps loop**: data changes drive retraining, CI validates and packages the model, and
**blue‑green** releases push it to Azure with near‑zero downtime and instant rollback. The
architecture’s ports‑and‑adapters discipline let us evolve the hardest infrastructure decision
(persistence) without touching business logic — the clearest evidence that the design met its goal.

---

### Appendix A — reproduce the numbers

```bash
python ml/dataset.py                       # dataset size + class counts
python ml/train_role_classifier.py         # trains, writes models/.../vN + metrics.json
cat models/job_role_classifier/v2/metrics.json   # accuracy, F1, per-class, confusion matrix
python -m pytest tests/ -q                 # unit suite
python testing/scripts/pipeline_eval.py    # offline match/AI evaluation
```

### Appendix B — key facts table

| Item | Value |
|------|-------|
| Jobs (unique) | 1,129 |
| Classes | 11 |
| Train / Test | 903 / 226 |
| Accuracy | 0.889 |
| Macro‑F1 | 0.877 |
| Weighted‑F1 | 0.889 |
| CV macro‑F1 | 0.836 ± 0.023 |
| Model | TF‑IDF(1–2g) + LogisticRegression(C=2.0, balanced) |
| Embeddings | all‑MiniLM‑L6‑v2 (384‑dim) |
| Cloud | Azure Container Apps + PostgreSQL Flexible Server + ACR |
| Release | Blue‑green revision traffic shift, health‑gated |
