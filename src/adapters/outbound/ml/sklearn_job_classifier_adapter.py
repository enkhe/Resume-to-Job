from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from src.ports.output.job_classifier import JobCategoryPrediction, JobClassifierPort

_DEFAULT_MODEL_DIR = (
    Path(__file__).resolve().parents[4] / "models" / "job_role_classifier"
)


class SklearnJobClassifierAdapter(JobClassifierPort):
    """Load the latest trained job-role classifier (sklearn Pipeline) and predict.

    Resolves the active version from ``models/job_role_classifier/registry.json``.
    Degrades gracefully: if no artifact is present (model not trained yet), or
    scikit-learn/joblib are unavailable, ``is_ready()`` returns False and the app
    can hide the prediction column instead of crashing.
    """

    def __init__(self, model_dir: str | Path = _DEFAULT_MODEL_DIR) -> None:
        self._model_dir = Path(model_dir)
        self._pipeline = None
        self.version: str | None = None
        self.metadata: dict = {}
        self.metrics: dict = {}
        self._load_latest()

    def _load_latest(self) -> None:
        registry = self._model_dir / "registry.json"
        if not registry.exists():
            return
        try:
            latest = json.loads(registry.read_text()).get("latest")
            if not latest:
                return
            vdir = self._model_dir / latest
            import joblib  # local import so the app runs even without sklearn installed

            self._pipeline = joblib.load(vdir / "model.joblib")
            self.version = latest
            meta_path = vdir / "metadata.json"
            metrics_path = vdir / "metrics.json"
            if meta_path.exists():
                self.metadata = json.loads(meta_path.read_text())
            if metrics_path.exists():
                self.metrics = json.loads(metrics_path.read_text())
        except Exception:
            # Any load failure -> treat as "no model"; UI falls back cleanly.
            self._pipeline = None
            self.version = None

    def is_ready(self) -> bool:
        return self._pipeline is not None

    def predict(self, texts: Sequence[str]) -> list[JobCategoryPrediction]:
        if self._pipeline is None or not texts:
            return []
        labels = list(self._pipeline.predict(texts))
        confidences: list[float]
        if hasattr(self._pipeline, "predict_proba"):
            proba = self._pipeline.predict_proba(texts)
            confidences = [float(max(row)) for row in proba]
        else:
            confidences = [float("nan")] * len(labels)
        return [
            JobCategoryPrediction(category=str(label), confidence=conf)
            for label, conf in zip(labels, confidences)
        ]
