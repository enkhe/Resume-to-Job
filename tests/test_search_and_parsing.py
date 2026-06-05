"""Fast, dependency-light unit tests (no model downloads, no network).

Covers the pieces CI must protect: JSearch parsing/dedup, the lexical keyword
index, and the keyword-vs-semantic comparison mechanics.
"""
from __future__ import annotations

import math

from src.adapters.inbound.api_provider.jsearch_job_parser import JSearchJobParser
from src.adapters.outbound.search.tfidf_keyword_search import TfidfKeywordSearch
from src.application.use_cases.search_jobs import SearchJobsUseCase
from src.domain.entities.Job import Job
from src.domain.services.similarity import cosine_similarity


def _job(jid, title, desc, emb=None):
    return Job(id=jid, title=title, company="ACME", description=desc, embedding=emb)


class FakeEmbedding:
    """Deterministic offline embedding: 3 dims = counts of three marker words."""

    VOCAB = ("security", "data", "frontend")

    def embed_texts(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            out.append([float(low.count(w)) + 0.01 for w in self.VOCAB])
        return out


def test_cosine_similarity_basics():
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert abs(cosine_similarity([1, 0], [0, 1])) < 1e-9
    assert cosine_similarity([], [1]) == 0.0  # mismatched/empty -> 0


def test_jsearch_parser_handles_both_envelopes_and_dedup():
    parser = JSearchJobParser()
    rec = {"job_id": "A", "job_title": "Dev", "employer_name": "Co",
           "job_description": "d", "job_city": "NYC", "job_state": "NY"}
    search_v1 = {"data": [rec]}
    search_v2 = {"data": {"jobs": [rec], "cursor": "x"}}
    assert len(parser.extract_list(search_v1)) == 1
    assert len(parser.extract_list(search_v2)) == 1  # nested {jobs:[...]} envelope

    norm = parser.to_normalized_records(search_v1)[0]
    assert norm["id"] == "A" and norm["company"] == "Co" and norm["location"] == "NYC, NY"

    deduped = parser.dedupe_by_id(parser.to_full_records({"data": [rec, rec]}))
    assert len(deduped) == 1  # same job_id collapses


def test_remote_location_mapping():
    parser = JSearchJobParser()
    rec = {"job_id": "B", "job_title": "T", "employer_name": "C",
           "job_description": "d", "job_is_remote": True, "job_city": "Austin"}
    assert parser.to_normalized_records({"data": [rec]})[0]["location"] == "Remote"


def test_keyword_index_only_matches_shared_terms():
    idx = TfidfKeywordSearch().fit(
        ["python backend engineer", "react frontend developer", "cybersecurity soc analyst"]
    )
    hits = idx.search("frontend react", top_k=3)
    assert hits, "expected at least one lexical hit"
    assert hits[0][0] == 1  # row 1 is the react/frontend job
    # A query with no shared vocabulary returns nothing — the keyword 'gap'.
    assert idx.search("zzzz qqqq", top_k=3) == []


def test_compare_separates_semantic_only_from_overlap():
    jobs = [
        _job("sec", "SOC Analyst", "security incident response", emb=[5.0, 0.0, 0.0]),
        _job("data", "Data Analyst", "data dashboards sql", emb=[0.0, 5.0, 0.0]),
        _job("fe", "Frontend Dev", "frontend react ui", emb=[0.0, 0.0, 5.0]),
    ]
    uc = SearchJobsUseCase(FakeEmbedding()).index(jobs)

    # "security" appears literally in the SOC job -> keyword finds it too.
    cmp_kw = uc.compare("security", top_k=3)
    assert cmp_kw.keyword and cmp_kw.keyword[0].job.id == "sec"
    assert cmp_kw.semantic[0].job.id == "sec"
    assert "sec" in cmp_kw.overlap_ids

    # A paraphrase with no shared words -> keyword misses, semantic still ranks sec top.
    cmp_para = uc.compare("protect against intruders", top_k=3)
    assert cmp_para.semantic[0].job.id == "sec"
    assert cmp_para.keyword == []
    assert "sec" in cmp_para.semantic_only_ids  # surfaced by semantic, missed by keyword


def test_semantic_ranking_is_sorted_desc():
    jobs = [
        _job("a", "A", "data", emb=[0.0, 1.0, 0.0]),
        _job("b", "B", "security", emb=[1.0, 0.0, 0.0]),
    ]
    uc = SearchJobsUseCase(FakeEmbedding()).index(jobs)
    hits = uc.semantic_search("data", top_k=2)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
