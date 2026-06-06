# Training the Model — End-to-End Walkthrough

A practical, reproducible walkthrough of **how the job-role classifier is trained, what files it
produces, where they live, and which parts of the app use them**. For the deeper reference docs see
[training pipeline](training-pipeline.md) (dataset/labels internals), [model card](model-card.md)
(spec/metrics), and [model usage](model-usage.md) (runtime usage).

---

## 1. Prerequisites

The training data is the **committed JSearch harvest** under `data/jsearch_raw/` (122 raw responses
+ a `manifest.json`). Labels come *for free* from that manifest — each job is labeled with the
canonical category of the role query that surfaced it ([ml/dataset.py](../../ml/dataset.py)), so no
manual annotation is needed.

```bash
pip install -r requirements.txt -r requirements-dev.txt   # scikit-learn, joblib, etc.
```

---

## 2. How to train

There are three equivalent ways to run the exact same training pipeline:

### a) CLI (what produces a new version locally)
```bash
python ml/train_role_classifier.py
# tunables:
python ml/train_role_classifier.py --test-size 0.2 --C 2.0 --cv-folds 5
```
What it does ([ml/train_role_classifier.py](../../ml/train_role_classifier.py)):
1. `build_dataset()` rebuilds the labeled set from `data/jsearch_raw/` → ~1,129 jobs, 11 categories,
   with a `data_fingerprint`.
2. Stratified train/test split, 5-fold CV on the train split for a robustness signal.
3. Fits a scikit-learn `Pipeline`: `TfidfVectorizer` (1–2 grams, English stop-words, sublinear TF) →
   `LogisticRegression` (`class_weight="balanced"`).
4. Writes a **new versioned artifact** and updates the registry pointer.

### b) Streamlit UI — Model Ops page
The **"Retrain model now"** button on [pages/5_Model_Ops.py](../../pages/5_Model_Ops.py) runs the
same script in a subprocess, clears caches, and reloads the new version. The page also shows
**drift detection** (current dataset fingerprint vs. the active model's).

### c) CI/CD
On `main` with `ENABLE_DEPLOY=true`, the pipeline trains the model and bakes it into the image
([.github/workflows/ci-cd.yml](../../.github/workflows/ci-cd.yml), "Train model" step).

---

## 3. What files get produced

Each training run creates a new `v{N}/` folder and updates `registry.json`:

| File | Size (approx) | Contents |
|------|---------------|----------|
| `models/job_role_classifier/v{N}/model.joblib` | ~2.6 MB | The serialized TF-IDF + LogisticRegression pipeline (the actual model). |
| `models/job_role_classifier/v{N}/metrics.json` | ~3.7 KB | accuracy, F1 (macro/weighted), CV scores, per-class report, confusion matrix. |
| `models/job_role_classifier/v{N}/metadata.json` | ~710 B | version, `trained_at`, classes, hyperparameters, `data_fingerprint`, sklearn version. |
| `models/job_role_classifier/registry.json` | small | `{"latest": "vN", "versions": [...]}` — the pointer the app reads. |

Artifacts are small and **committable** (they're checked into the repo), which is what lets CI bake
the trained model straight into the container image.

---

## 4. Where it lives

```
models/job_role_classifier/
├── registry.json          # { "latest": "v2", "versions": [v1, v2] }
├── v1/
│   ├── model.joblib
│   ├── metrics.json
│   └── metadata.json
└── v2/                    # ← latest (what the app serves)
    ├── model.joblib
    ├── metrics.json
    └── metadata.json
```

Current state: **`v2` is `latest`** — accuracy **0.889**, F1-macro **0.877**, trained on 903 / tested
on 226 jobs across **11 categories**. Older versions are retained (immutable), so rollback is just
pointing `registry.json` `latest` back to a previous version.

---

## 5. How it's loaded and used

The single load/predict point is **`SklearnJobClassifierAdapter`**
([src/adapters/outbound/ml/sklearn_job_classifier_adapter.py](../../src/adapters/outbound/ml/sklearn_job_classifier_adapter.py)):
it reads `registry.json` → `latest` → `joblib.load(v{N}/model.joblib)`, then `predict()` returns a
`(category, confidence)` per input (`"<title>. <description>"`). If no artifact is present it
degrades gracefully (`is_ready() == False`) and the UI hides the feature.

### Pages / features that use the model

| Page / feature | How the model is used | Code |
|----------------|-----------------------|------|
| **Home** | "Role-classifier model" metric, e.g. `v2 (89% acc)` | [app.py](../../app.py) |
| **Dashboard** | `predicted_role` column on the job catalog **and** a "Role-category mix (model-predicted)" breakdown across the whole corpus | [dashboard_app.py](../../src/adapters/inbound/streamlit/dashboard_app.py) |
| **Job Search** | `predicted_role` column on each search result (keyword and semantic hits) | [job_search_app.py](../../src/adapters/inbound/streamlit/job_search_app.py) |
| **Model Ops** | Registry/metrics view, drift detection, and the **Retrain** button | [pages/5_Model_Ops.py](../../pages/5_Model_Ops.py) |

> Note: the classifier (role tagging) is **separate** from the embeddings used for Job Search ranking
> and Resume Matching — those use sentence-transformer vectors + cosine similarity, not this model.
> See [model usage](model-usage.md#classifier-vs-embeddings).

---

## 6. The full loop

```
data/jsearch_raw/ ──(ml/dataset.py)──► labeled dataset (fingerprint)
        │
        ▼
python ml/train_role_classifier.py ──► models/job_role_classifier/v{N}/model.joblib
        │                                        + metrics.json + metadata.json
        ▼                                        + registry.json (latest = vN)
SklearnJobClassifierAdapter (loads latest) ──► Home · Dashboard · Job Search · Model Ops
```

See [lifecycle](lifecycle.md) for how a new harvest triggers retraining and how a new version flows
through CI/CD to the Azure deployment.
