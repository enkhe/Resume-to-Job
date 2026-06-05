from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class JobCategoryPrediction:
    """A single role-category prediction with confidence."""

    __slots__ = ("category", "confidence")

    def __init__(self, category: str, confidence: float) -> None:
        self.category = category
        self.confidence = confidence


class JobClassifierPort(Protocol):
    """Contract for predicting a job's role category from its text.

    The application/UI depends on this interface, not on scikit-learn.
    """

    def is_ready(self) -> bool:
        """Whether a trained model artifact is loaded and usable."""
        raise NotImplementedError

    def predict(self, texts: Sequence[str]) -> list[JobCategoryPrediction]:
        """Predict (category, confidence) for each input text."""
        raise NotImplementedError
