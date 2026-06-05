# MLOps Lifecycle

The end-to-end loop that ties data, model, and deployment together.

```
ingest new jobs ──► dataset fingerprint changes ──► retrain ──► new model version
      (JSearch)            (ml/dataset.py)         (ml/train_*)   (registry.json: latest=vN)
                                                                         │
                                          ┌──────────────────────────────┘
                                          ▼
                              CI: build · test · train ──► image ──► deploy (Azure)
```

## Trigger: new data
Ingesting postings (UI or harvester) changes the set of `(job_id, label)` pairs, which changes the
dataset **fingerprint**. The **Model Ops** page ([5_Model_Ops.py](../../pages/5_Model_Ops.py))
compares the current dataset fingerprint to the active model's `data_fingerprint`:

- match → ✅ "Model is up to date with the harvested data".
- differ → ⚠️ "New data detected … retrain to update the model".

This is lightweight **data-drift detection**: it tells you when the model is stale relative to the
corpus.

## Action: retrain
Two equivalent ways to produce a new version:
- **UI:** the "Retrain model now" button (runs the training script in a subprocess, clears caches,
  reloads the new version).
- **CLI / CI:** `python ml/train_role_classifier.py`.

Each retrain registers a new `vN` in the [registry](training-pipeline.md#3-versioning--registry).
Versions are immutable; the registry's `latest` pointer is what the app serves.

## Promotion: build & deploy
On `main` (with `ENABLE_DEPLOY=true`), the [CI/CD pipeline](../operations/ci-cd.md):
1. Trains the model and uploads it as an artifact.
2. Builds the Docker image with the trained model baked in.
3. Pushes to Azure Container Registry and updates the Azure Container App.

## Rollback
Because every version is retained under `models/job_role_classifier/vN/`, rolling back is editing
`registry.json`'s `latest` to a previous version and redeploying. (A future enhancement is a
metrics gate that refuses to promote a version whose F1 regresses beyond a threshold.)

## Roadmap
- MLflow tracking/registry for richer experiment history.
- Scheduled retrain (cron / GitHub Actions schedule) after each harvest.
- Promotion gate on held-out metrics; champion/challenger comparison.
