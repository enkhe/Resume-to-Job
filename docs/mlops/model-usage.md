# Model Usage — How the Job-Role Classifier Is Used in the App

This page explains **what the trained model is for and where it runs in the application**. For the
model spec and metrics see the [model card](model-card.md); for how it is trained and versioned see
the [training pipeline](training-pipeline.md); for the retrain→deploy loop see the
[lifecycle](lifecycle.md).

---

## What it does

The `job_role_classifier` predicts a job's **role category** from its text (`title + description`).
It is the project's *owned, retrainable* ML model — the thing the MLOps pipeline operationalizes —
and is **separate from search/matching** (see [Classifier vs. embeddings](#classifier-vs-embeddings)).

- **Input:** a list of strings, each `"<title>. <description>"`.
- **Output:** for each input, a predicted `category` plus a `confidence` (max class probability).
- **Classes (11):** Software Engineering, Frontend, Backend, Full Stack, Data & Analytics,
  Machine Learning / AI, Cloud & DevOps, Cybersecurity, IT Infrastructure & Support, QA & Testing,
  Mobile.

---

## How it loads

`SklearnJobClassifierAdapter`
([src/adapters/outbound/ml/sklearn_job_classifier_adapter.py](../../src/adapters/outbound/ml/sklearn_job_classifier_adapter.py))
implements the `JobClassifierPort`. On construction it:

1. reads `models/job_role_classifier/registry.json` to find the `latest` version,
2. `joblib.load`s that version's `model.joblib` (the TF-IDF + LogisticRegression pipeline),
3. loads its `metadata.json` / `metrics.json` for the UI badges.

It **degrades gracefully**: if no artifact is present (model not trained yet) or scikit-learn/joblib
are unavailable, `is_ready()` returns `False` and the UI hides the model features instead of
crashing.

```python
clf = SklearnJobClassifierAdapter()
if clf.is_ready():
    preds = clf.predict([f"{job.title}. {job.description}"])
    # -> [JobCategoryPrediction(category="Backend", confidence=0.91)]
```

---

## Where it appears in the UI

The classifier is consumed on **four surfaces**:

| Surface | What it shows | Code |
|---------|---------------|------|
| **Home** (`app.py`) | "Role-classifier model" metric, e.g. `v2 (89% acc)` | [app.py](../../app.py) |
| **Dashboard** | A `predicted_role` column on every job in the catalog, plus a **"Role-category mix (model-predicted)"** breakdown across the whole corpus, plus a model badge (version, accuracy, #classes) | [dashboard_app.py](../../src/adapters/inbound/streamlit/dashboard_app.py) |
| **Job Search** | A `predicted_role` column on each search result (keyword and semantic hits alike) | [job_search_app.py](../../src/adapters/inbound/streamlit/job_search_app.py) |
| **Model Ops** | Registry/metrics view, **drift detection** (compares the model's `data_fingerprint` to the current dataset), and the **Retrain** action that produces a new version | [pages/5_Model_Ops.py](../../pages/5_Model_Ops.py) |

> The classifier is **read-only** at inference time — predictions are computed on the fly for
> display and are not written back to the `jobs` table.

---

## Classifier vs. embeddings

A common point of confusion: the project uses **two different ML components** for different jobs.

| | Job-role classifier | Sentence embeddings |
|---|---|---|
| **Purpose** | Tag a job with a role category | Semantic search & resume matching |
| **Model** | TF-IDF + LogisticRegression (owned, versioned) | sentence-transformers (pretrained) |
| **Where stored** | `models/job_role_classifier/vN/` | `embedding` column in the jobs store (Postgres/SQLite) |
| **Used by** | Dashboard tagging / category mix | Job Search (semantic) and Job Matching (cosine similarity) |

The classifier is the **MLOps centerpiece** (trained, versioned, retrainable, deploy trigger);
embeddings power retrieval but are not retrained here.

---

## Related

- [Model card](model-card.md) — spec, metrics, intended use, limitations
- [Training pipeline](training-pipeline.md) — dataset, weak labels, training, versioning
- [Lifecycle](lifecycle.md) — ingest → retrain → build → deploy, drift detection, rollback
