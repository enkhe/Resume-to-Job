from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.adapters.outbound.search.tfidf_keyword_search import TfidfKeywordSearch
from src.domain.entities.Job import Job
from src.domain.services.similarity import cosine_similarity
from src.ports.output.embedding_service import EmbeddingServicePort


@dataclass(frozen=True, slots=True)
class SearchHit:
    job: Job
    score: float


@dataclass(frozen=True, slots=True)
class SearchComparison:
    query: str
    keyword: list[SearchHit]
    semantic: list[SearchHit]
    semantic_only_ids: set[str]   # surfaced by semantic, missed by keyword
    keyword_only_ids: set[str]
    overlap_ids: set[str]


def job_text(job: Job) -> str:
    return f"{job.title}. {job.description or ''}".strip()


class SearchJobsUseCase:
    """Compare lexical (keyword/TF-IDF) and semantic (embedding) retrieval.

    The keyword index is fit once over the corpus; semantic search reuses the
    embeddings already stored on each Job. ``compare`` runs both for one query
    so the UI can show, side by side, where meaning-based search beats
    vocabulary-based search.
    """

    def __init__(self, embedding_service: EmbeddingServicePort) -> None:
        self._embeddings = embedding_service
        self._keyword = TfidfKeywordSearch()
        self._jobs: list[Job] = []

    def index(self, jobs: Sequence[Job]) -> "SearchJobsUseCase":
        self._jobs = list(jobs)
        if self._jobs:
            self._keyword.fit([job_text(j) for j in self._jobs])
        return self

    def keyword_search(self, query: str, top_k: int = 8) -> list[SearchHit]:
        hits = self._keyword.search(query, top_k=top_k)
        return [SearchHit(job=self._jobs[idx], score=score) for idx, score in hits]

    def semantic_search(self, query: str, top_k: int = 8) -> list[SearchHit]:
        if not query.strip() or not self._jobs:
            return []
        vectors = self._embeddings.embed_texts([query])
        if not vectors:
            return []
        query_vec = vectors[0]
        scored: list[SearchHit] = []
        for job in self._jobs:
            if job.embedding is None:
                continue
            scored.append(SearchHit(job=job, score=cosine_similarity(query_vec, job.embedding)))
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def compare(self, query: str, top_k: int = 8) -> SearchComparison:
        keyword = self.keyword_search(query, top_k=top_k)
        semantic = self.semantic_search(query, top_k=top_k)
        kw_ids = {hit.job.id for hit in keyword}
        se_ids = {hit.job.id for hit in semantic}
        return SearchComparison(
            query=query,
            keyword=keyword,
            semantic=semantic,
            semantic_only_ids=se_ids - kw_ids,
            keyword_only_ids=kw_ids - se_ids,
            overlap_ids=se_ids & kw_ids,
        )
