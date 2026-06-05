from __future__ import annotations

from collections.abc import Sequence


class TfidfKeywordSearch:
    """Lexical (keyword) search over job texts using TF-IDF + cosine.

    This is the *bag-of-words* baseline: it only scores jobs that share literal
    terms (words / bigrams) with the query. It has no notion of meaning, so a
    query like "keep hackers out" won't match a posting that says
    "SIEM, threat detection, incident response" — which is exactly the gap the
    semantic (embedding) search is meant to fill.
    """

    def __init__(self) -> None:
        self._vectorizer = None
        self._matrix = None
        self._fitted = False

    def fit(self, texts: Sequence[str]) -> "TfidfKeywordSearch":
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform(list(texts))
        self._fitted = True
        return self

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """Return ``(row_index, score)`` for the top_k matches, best first.

        Rows with a zero score (no shared terms) are dropped — that absence is
        the point of the keyword/semantic contrast, so callers can show it.
        """
        if not self._fitted or not query.strip():
            return []
        from sklearn.metrics.pairwise import linear_kernel

        query_vec = self._vectorizer.transform([query])
        # TF-IDF rows are L2-normalized, so linear_kernel == cosine similarity.
        scores = linear_kernel(query_vec, self._matrix).ravel()
        ranked = sorted(
            ((idx, float(score)) for idx, score in enumerate(scores) if score > 0.0),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return ranked[:top_k]
