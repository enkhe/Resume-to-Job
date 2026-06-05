from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from src.adapters.outbound.ml.sklearn_job_classifier_adapter import (
    SklearnJobClassifierAdapter,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MODEL_DIR = REPO_ROOT / "models" / "job_role_classifier"
TRAIN_SCRIPT = REPO_ROOT / "ml" / "train_role_classifier.py"


def _current_data_fingerprint() -> tuple[str | None, int]:
    """Fingerprint of the *current* harvested dataset, to detect new data."""
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from ml.dataset import build_dataset

        ds = build_dataset()
        return ds.data_fingerprint, len(ds)
    except Exception:
        return None, 0


def _run_training() -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(TRAIN_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode == 0, (proc.stdout + "\n" + proc.stderr)


def streamlit_app() -> None:
    st.title("Model Ops — Job-Role Classifier")
    st.caption(
        "The owned ML model: an scikit-learn pipeline (TF-IDF + Logistic Regression) trained on the "
        "harvested jobs. Ingest new postings → retrain → a new versioned model artifact (`model.joblib`). "
        "In CI this retrain runs automatically on every data change (see the build pipeline)."
    )

    clf = SklearnJobClassifierAdapter()

    if not clf.is_ready():
        st.warning("No trained model found yet.")
        st.code("python ml/train_role_classifier.py", language="bash")
    else:
        meta, metrics = clf.metadata, clf.metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Active version", clf.version or "—")
        acc = metrics.get("accuracy")
        c2.metric("Accuracy", f"{acc:.1%}" if isinstance(acc, (int, float)) else "—")
        f1 = metrics.get("f1_macro")
        c3.metric("F1 (macro)", f"{f1:.3f}" if isinstance(f1, (int, float)) else "—")
        c4.metric("Trained on", f"{meta.get('n_samples', '—')} jobs")
        st.caption(
            f"Model type: `{meta.get('model_type', '?')}` · trained {meta.get('trained_at', '?')} · "
            f"data fingerprint `{meta.get('data_fingerprint', '?')}`"
        )

    # --- Drift / new-data detection -------------------------------------------------
    current_fp, current_n = _current_data_fingerprint()
    model_fp = clf.metadata.get("data_fingerprint") if clf.is_ready() else None
    st.divider()
    st.subheader("Data → Model freshness")
    if current_fp is None:
        st.info("No harvested dataset found to evaluate freshness.")
    elif model_fp == current_fp:
        st.success(
            f"✅ Model is up to date with the harvested data "
            f"({current_n} labeled jobs, fingerprint `{current_fp}`)."
        )
    else:
        st.warning(
            f"⚠️ New data detected. Current dataset ({current_n} jobs, `{current_fp}`) "
            f"differs from the model's training data (`{model_fp}`). Retrain to update the model."
        )

    # --- Retrain trigger ------------------------------------------------------------
    st.subheader("Retrain")
    st.caption("Rebuilds the dataset from the harvest cache and registers a new model version.")
    if st.button("🔁 Retrain model now", type="primary"):
        with st.spinner("Training… (rebuild dataset → fit → evaluate → register new version)"):
            ok, output = _run_training()
        if ok:
            st.cache_resource.clear()  # refresh classifier/search caches app-wide
            st.success("Retraining complete — a new model version was registered.")
            with st.expander("Training log"):
                st.code(output)
            st.rerun()
        else:
            st.error("Retraining failed. See log below.")
            st.code(output)

    # --- Registry -------------------------------------------------------------------
    st.divider()
    st.subheader("Model registry")
    registry_path = MODEL_DIR / "registry.json"
    if registry_path.exists():
        registry = json.loads(registry_path.read_text())
        versions = list(reversed(registry.get("versions", [])))
        if versions:
            df = pd.DataFrame(versions)
            df["active"] = df["version"].apply(lambda v: "⭐" if v == registry.get("latest") else "")
            st.dataframe(df, hide_index=True, use_container_width=True)
        st.caption(f"Registry: `models/job_role_classifier/registry.json` · latest = **{registry.get('latest')}**")
    else:
        st.info("No registry yet — train a model to create one.")

    # --- Per-class metrics + confusion matrix --------------------------------------
    if clf.is_ready() and clf.metrics.get("per_class"):
        with st.expander("Per-class metrics & confusion matrix"):
            per_class = clf.metrics["per_class"]
            rows = [
                {
                    "category": cat,
                    "precision": round(m.get("precision", 0), 3),
                    "recall": round(m.get("recall", 0), 3),
                    "f1": round(m.get("f1-score", 0), 3),
                    "support": int(m.get("support", 0)),
                }
                for cat, m in per_class.items()
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            cm = clf.metrics.get("confusion_matrix")
            if cm:
                cm_df = pd.DataFrame(cm["matrix"], index=cm["labels"], columns=cm["labels"])
                st.caption("Confusion matrix (rows = actual, columns = predicted)")
                st.dataframe(cm_df, use_container_width=True)
