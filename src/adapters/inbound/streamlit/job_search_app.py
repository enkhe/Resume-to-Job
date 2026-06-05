from __future__ import annotations

import pandas as pd
import streamlit as st

from src.adapters.outbound.embedding.sentence_transformers_adapter import (
    SentenceTransformersEmbeddingAdapter,
)
from src.adapters.outbound.ml.sklearn_job_classifier_adapter import (
    SklearnJobClassifierAdapter,
)
from src.adapters.outbound.persistence.repository_factory import (
    get_job_repository,
    job_store_available,
    job_store_cache_key,
)
from src.application.use_cases.search_jobs import SearchComparison, SearchJobsUseCase, job_text

# A query that uses everyday language a posting would never phrase literally —
# the clearest way to show semantic search beating keyword search.
_DEFAULT_QUERY = "keep hackers out of our systems"


@st.cache_resource(show_spinner="Building search indexes over the job corpus…")
def _build_search(store_key: str, job_count: int) -> tuple[SearchJobsUseCase, list]:
    """Load jobs once and fit the keyword index. Cached per (store, job_count)."""
    repo = get_job_repository()
    jobs = repo.find_page(offset=0, limit=max(job_count, 1))
    repo.close()
    use_case = SearchJobsUseCase(SentenceTransformersEmbeddingAdapter()).index(jobs)
    return use_case, jobs


@st.cache_resource(show_spinner=False)
def _classifier() -> SklearnJobClassifierAdapter:
    return SklearnJobClassifierAdapter()


def _hits_to_df(hits, semantic_only_ids, classifier) -> pd.DataFrame:
    texts = [f"{h.job.title}. {h.job.description}" for h in hits]
    preds = classifier.predict(texts) if (classifier.is_ready() and texts) else []
    rows = []
    for i, h in enumerate(hits):
        rows.append(
            {
                "rank": i + 1,
                "score": round(h.score, 3),
                "title": h.job.title,
                "company": h.job.company,
                "predicted_role": preds[i].category if i < len(preds) else "",
                "location": h.job.location or "",
                "semantic_only": "🟢" if h.job.id in semantic_only_ids else "",
            }
        )
    return pd.DataFrame(rows)


def streamlit_app() -> None:
    st.title("Job Search — Keyword vs Semantic")
    st.caption(
        "The same query, two retrieval methods. **Keyword (TF-IDF)** matches shared words; "
        "**Semantic (embeddings)** matches meaning. Watch semantic win when the words don't line up."
    )

    if not job_store_available():
        st.warning("No job database found. Ingest jobs on the Data Ingestion page first.")
        return

    repo = get_job_repository()
    job_count = repo.count()
    repo.close()
    if job_count == 0:
        st.warning("No jobs in the database yet. Ingest jobs first.")
        return

    use_case, _jobs = _build_search(job_store_cache_key(), job_count)
    classifier = _classifier()

    with st.form("search_form"):
        query = st.text_input("Search query (try natural language, not job-posting jargon)", value=_DEFAULT_QUERY)
        col_a, col_b = st.columns([1, 3])
        top_k = col_a.slider("Results per method", 3, 15, 8)
        col_b.caption(
            "Examples that expose the gap: *“keep hackers out of our systems”*, "
            "*“teach computers to learn from data”*, *“make our website look good on phones”*."
        )
        submitted = st.form_submit_button("Search", type="primary", use_container_width=True)

    if not submitted:
        st.info("Enter a query and click **Search** to compare the two methods.")
        return

    cmp: SearchComparison = use_case.compare(query, top_k=top_k)

    m1, m2, m3 = st.columns(3)
    m1.metric("Keyword hits", len(cmp.keyword))
    m2.metric("Shared by both", len(cmp.overlap_ids))
    m3.metric("Semantic-only finds", len(cmp.semantic_only_ids),
              help="Relevant jobs semantic search surfaced that keyword search missed entirely.")

    if cmp.semantic_only_ids:
        only = [h for h in cmp.semantic if h.job.id in cmp.semantic_only_ids]
        st.success(
            f"🟢 Semantic search surfaced **{len(only)}** job(s) that keyword search missed — "
            "because they describe the role without using your exact words:\n\n"
            + "\n".join(f"- **{h.job.title}** · {h.job.company}" for h in only[:6])
        )

    left, right = st.columns(2)
    with left:
        st.markdown("#### 🔤 Keyword search (TF-IDF)")
        st.caption("Bag-of-words. Scores only jobs that share literal terms with the query.")
        if cmp.keyword:
            st.dataframe(_hits_to_df(cmp.keyword, cmp.semantic_only_ids, classifier),
                         hide_index=True, use_container_width=True)
        else:
            st.warning("No keyword matches — none of the jobs share your exact words. "
                       "This is exactly where semantic search helps.")
    with right:
        st.markdown("#### 🧠 Semantic search (embeddings)")
        st.caption("Dense vectors (all-MiniLM-L6-v2). Matches meaning, not just words.")
        st.dataframe(_hits_to_df(cmp.semantic, cmp.semantic_only_ids, classifier),
                     hide_index=True, use_container_width=True)
        st.caption("🟢 = surfaced here but missing from the keyword results.")
