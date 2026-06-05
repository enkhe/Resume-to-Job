#!/usr/bin/env python3
"""Train the job-role classifier and write a versioned model artifact + metrics.

This is the MLOps training pipeline. It is fully reproducible and *updatable*:
re-running it after a new harvest rebuilds the dataset from the raw cache and
produces a new model version, leaving prior versions in the registry.

    python ml/train_role_classifier.py
    python ml/train_role_classifier.py --test-size 0.25 --C 4.0

Artifacts (committable, small):
    models/job_role_classifier/v{N}/model.joblib    # TF-IDF + LogisticRegression pipeline
    models/job_role_classifier/v{N}/metrics.json    # accuracy, F1, per-class, confusion matrix, CV
    models/job_role_classifier/v{N}/metadata.json   # version, trained_at, classes, data fingerprint
    models/job_role_classifier/registry.json        # {"latest": "vN", "versions": [...]}
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.dataset import build_dataset  # noqa: E402

MODEL_DIR = REPO_ROOT / "models" / "job_role_classifier"
RANDOM_STATE = 42


def _next_version() -> str:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    existing = [int(p.name[1:]) for p in MODEL_DIR.glob("v*") if p.name[1:].isdigit()]
    return f"v{(max(existing) + 1) if existing else 1}"


def build_pipeline(c: float) -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    stop_words="english",
                    ngram_range=(1, 2),
                    min_df=2,
                    max_features=20000,
                    sublinear_tf=True,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    C=c,
                    class_weight="balanced",  # offset class imbalance
                ),
            ),
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test-size", type=float, default=0.2)
    ap.add_argument("--C", type=float, default=2.0, help="LogisticRegression inverse-regularization.")
    ap.add_argument("--cv-folds", type=int, default=5)
    args = ap.parse_args()

    ds = build_dataset()
    print(f"Dataset: {len(ds)} jobs, {len(ds.categories)} categories, fingerprint={ds.data_fingerprint}")
    if len(ds) < 50:
        print("Too few samples to train a meaningful model.")
        return 1

    X_train, X_test, y_train, y_test = train_test_split(
        ds.texts, ds.labels,
        test_size=args.test_size, random_state=RANDOM_STATE, stratify=ds.labels,
    )

    pipe = build_pipeline(args.C)

    # Cross-validation on the training split for a robustness signal.
    cv = StratifiedKFold(n_splits=args.cv_folds, shuffle=True, random_state=RANDOM_STATE)
    cv_scores = cross_val_score(pipe, X_train, y_train, cv=cv, scoring="f1_macro")

    pipe.fit(X_train, y_train)
    y_pred = pipe.predict(X_test)

    accuracy = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro")
    f1_weighted = f1_score(y_test, y_pred, average="weighted")
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    labels_sorted = sorted(set(ds.labels))
    cm = confusion_matrix(y_test, y_pred, labels=labels_sorted).tolist()

    print(f"\nHeld-out accuracy : {accuracy:.3f}")
    print(f"Held-out F1 (macro): {f1_macro:.3f}  |  F1 (weighted): {f1_weighted:.3f}")
    print(f"CV F1-macro       : {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")
    print("\nPer-class F1:")
    for cat in labels_sorted:
        print(f"  {report[cat]['f1-score']:.3f}  (n={int(report[cat]['support'])})  {cat}")

    version = _next_version()
    vdir = MODEL_DIR / version
    vdir.mkdir(parents=True, exist_ok=True)
    trained_at = datetime.now(timezone.utc).isoformat()

    joblib.dump(pipe, vdir / "model.joblib")
    (vdir / "metrics.json").write_text(json.dumps({
        "accuracy": round(accuracy, 4),
        "f1_macro": round(f1_macro, 4),
        "f1_weighted": round(f1_weighted, 4),
        "cv_f1_macro_mean": round(float(cv_scores.mean()), 4),
        "cv_f1_macro_std": round(float(cv_scores.std()), 4),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "per_class": {c: report[c] for c in labels_sorted},
        "confusion_matrix": {"labels": labels_sorted, "matrix": cm},
    }, indent=2))
    (vdir / "metadata.json").write_text(json.dumps({
        "version": version,
        "model_name": "job_role_classifier",
        "trained_at": trained_at,
        "model_type": "TfidfVectorizer + LogisticRegression (sklearn Pipeline)",
        "sklearn_version": sklearn.__version__,
        "n_samples": len(ds),
        "classes": labels_sorted,
        "label_source": ds.label_source,
        "data_fingerprint": ds.data_fingerprint,
        "hyperparameters": {"C": args.C, "test_size": args.test_size, "ngram_range": [1, 2]},
    }, indent=2))

    # Update the registry (model registry pointer for the app + CD).
    registry_path = MODEL_DIR / "registry.json"
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {"versions": []}
    registry["latest"] = version
    registry.setdefault("versions", [])
    registry["versions"].append({
        "version": version,
        "trained_at": trained_at,
        "accuracy": round(accuracy, 4),
        "f1_macro": round(f1_macro, 4),
        "data_fingerprint": ds.data_fingerprint,
    })
    registry_path.write_text(json.dumps(registry, indent=2))

    print(f"\nSaved {version} -> {vdir}")
    print(f"Registry latest -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
