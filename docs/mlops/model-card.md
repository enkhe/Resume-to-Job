# Model Card — Job-Role Classifier

## Overview
- **Name:** `job_role_classifier`
- **Task:** Multiclass text classification — predict a job's **role category** from its title + description.
- **Type:** scikit-learn `Pipeline` = `TfidfVectorizer` (1–2 grams, English stop-words, sublinear TF) →
  `LogisticRegression` (`class_weight="balanced"`).
- **Artifact:** `models/job_role_classifier/<version>/model.joblib` (the serialized "pkl").
- **Owner:** Team 3, AI 510.

## Intended use
Auto-tag ingested jobs by role category in the Dashboard and enrich search results. It is a
lightweight, interpretable baseline — **not** a hiring or ranking decision system.

## Classes (11)
`Software Engineering`, `Frontend`, `Backend`, `Full Stack`, `Data & Analytics`,
`Machine Learning / AI`, `Cloud & DevOps`, `Cybersecurity`, `IT Infrastructure & Support`,
`QA & Testing`, `Mobile`.

## Training data
1,129 unique IT jobs harvested from JSearch. **Labels are derived for free** from the harvest
manifest: each job is labeled with the canonical category of the role query that surfaced it
(majority vote when multiple queries returned the same job). See
[training pipeline](training-pipeline.md). The dataset carries a `data_fingerprint` so the app can
detect when new data diverges from the trained model.

## Metrics (held-out test split, v1/v2)
| Metric | Value |
|--------|-------|
| Accuracy | **0.889** |
| F1 (macro) | **0.877** |
| F1 (weighted) | 0.889 |
| CV F1-macro (5-fold) | 0.836 ± 0.023 |

Per-class F1 ranges ~0.78–0.97 (highest: Cybersecurity, IT Infrastructure & Support; lowest:
Backend, ML/AI). Full per-class report and confusion matrix are in each version's `metrics.json`
and on the **Model Ops** page.

## Limitations
- Labels are **weak/distant supervision** from search queries, not human annotation — a job can be
  genuinely cross-category (e.g. "Full-stack + ML"), which caps separability between adjacent
  classes (Frontend / Full Stack; the three former data roles collapsed into Data & Analytics).
- TF-IDF is lexical: it generalizes to vocabulary it saw during training, not to unseen jargon.
- Trained on US IT postings from one harvest window; not representative of other markets/eras.

## Maintenance
Retrain whenever new jobs are ingested (`python ml/train_role_classifier.py` or the **Model Ops**
retrain button). Each run registers a new version in `registry.json`. See
[lifecycle](lifecycle.md).
