# Training Pipeline

Two files implement the reproducible, versioned training pipeline:

- [ml/dataset.py](../../ml/dataset.py) — builds the labeled dataset from the harvest.
- [ml/train_role_classifier.py](../../ml/train_role_classifier.py) — trains, evaluates, and registers a model.

## 1. Dataset build (labels for free)

Every harvested job was returned by a specific **role query**, recorded in
`data/jsearch_raw/manifest.json`. `build_dataset()`:

1. Reads the manifest to map each raw file → its role query.
2. Maps each fine-grained role → a canonical **category** (`ROLE_TO_CATEGORY`).
3. For each unique `job_id`, assigns the **majority category** across the queries that surfaced it.
4. Builds `text = title + ". " + description[:2000]` and a `data_fingerprint` (hash of ids+labels).

Inspect it directly:
```bash
python ml/dataset.py
# Dataset: 1129 labeled jobs across 11 categories
```

This is the project's **owned dataset**: it regenerates from the raw cache, so every new harvest
expands it and the model can be retrained.

## 2. Train, evaluate, register

```bash
python ml/train_role_classifier.py                 # defaults
python ml/train_role_classifier.py --C 4.0 --test-size 0.25
```

Steps:
1. Stratified train/test split (default 80/20, `random_state=42`).
2. Build the `Pipeline` (TF-IDF → LogisticRegression, balanced).
3. 5-fold stratified CV (F1-macro) on the training split for a robustness signal.
4. Fit on train, evaluate on the held-out test split.
5. Write a **new version** under `models/job_role_classifier/vN/`.

## 3. Versioning & registry

Each run produces:
- `model.joblib` — the serialized pipeline.
- `metrics.json` — accuracy, F1 (macro/weighted), per-class report, confusion matrix, CV scores.
- `metadata.json` — version, `trained_at`, classes, sklearn version, hyperparameters, `data_fingerprint`.

…and updates `registry.json`:
```json
{ "latest": "v2", "versions": [ { "version": "v1", "accuracy": 0.8894, "f1_macro": 0.8774, "data_fingerprint": "273cfdd2..." }, ... ] }
```

The app always loads `registry.json["latest"]` via
[SklearnJobClassifierAdapter](../../src/adapters/outbound/ml/sklearn_job_classifier_adapter.py),
degrading gracefully (hides predictions) if no artifact exists.

## 4. In CI

The same `python ml/train_role_classifier.py` runs in the
[CI/CD workflow](../operations/ci-cd.md): tests pass → the model is re-trained from the committed
dataset → the artifact is uploaded and baked into the deployed image. This is what makes
"ingest new data → produce a new model" an **automated build step**, not a manual one.

> CI training requires the harvested dataset (`data/jsearch_raw/` + `manifest.json`) to be
> committed. If absent, CI skips training and ships the committed model.
