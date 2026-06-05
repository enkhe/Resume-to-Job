from __future__ import annotations

import os

import pandas as pd

from src.adapters.inbound.api_provider.api_client import fetch_jobs
from src.adapters.inbound.api_provider.api_job_parser import ApiJobParser
from src.adapters.inbound.api_provider.jsearch_client import search_jobs
from src.adapters.inbound.api_provider.jsearch_job_parser import JSearchJobParser
from src.adapters.inbound.file_upload.dataframe_job_parser import DataFrameJobParser
from src.adapters.outbound.embedding.sentence_transformers_adapter import (
    SentenceTransformersEmbeddingAdapter,
)
from src.application.use_cases.ingest_jobs_batch import IngestJobsBatchUseCase
from src.domain.entities.Job import Job
from src.ports.output.job_repository import JobRepositoryPort
from pathlib import Path
from src.adapters.outbound.persistence.sqlite_job_repository import SQLiteJobRepository
from src.adapters.outbound.persistence.repository_factory import get_job_repository


class FakeJobRepository(JobRepositoryPort):
    """Tiny in-memory repository for demos and tests."""

    def __init__(self) -> None:
        self._store: dict[str, Job] = {}
        self.batches: list[list[Job]] = []

    def upsert(self, job: Job) -> None:
        self.upsert_many([job])

    def upsert_many(self, jobs: list[Job]) -> None:
        self.batches.append(list(jobs))
        for job in jobs:
            self._store[job.id] = job

    def find_all(self) -> list[Job]:
        return list(self._store.values())

    def count_with_embeddings(self) -> int:
        return sum(1 for job in self._store.values() if job.embedding is not None)

    def count(self) -> int:
        return len(self._store)

    def find_page(self, *, offset: int, limit: int) -> list[Job]:
        jobs = sorted(
            self._store.values(),
            key=lambda job: (job.title, job.company, job.id),
        )
        return jobs[offset : offset + limit]


def run_demo() -> None:
    """Run a small demo from the command line."""
    db_path = Path("data/jobs.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo = SQLiteJobRepository(db_path)
    parser = DataFrameJobParser()
    dataframe = pd.DataFrame(
        [
            {
                "id": "JOB-001",
                "title": "Data Scientist",
                "company": "Acme Analytics",
                "description": "Analyze product usage data and build forecasting models.",
                "location": "Remote",
                "source": "demo",
            },
            {
                "id": "JOB-002",
                "title": "ML Engineer",
                "company": "Nova AI",
                "description": "Build training pipelines and deploy ranking models.",
                "location": "New York",
                "source": "demo",
            },
        ]
    )
    embedding_service = SentenceTransformersEmbeddingAdapter()
    jobs = parser.to_jobs(dataframe)
    usecase = IngestJobsBatchUseCase(repository=repo, batch_size=200, embedding_service=embedding_service)
    result = usecase.execute(jobs)
    print(result)


# Optional Streamlit integration helper.
# To use inside your Streamlit page, import `streamlit_app` and call it from the page script.
def streamlit_app():
    import streamlit as st

    st.title("Data Ingestion")
    st.caption("Data route: CSV / generic API / JSearch -> parser -> list[Job] -> embed -> batches of 200 -> shared DB (Postgres/SQLite)")

    source = st.radio(
        "Choose the ingestion source",
        ["CSV upload", "API endpoint", "JSearch (IT jobs)"],
        horizontal=True,
    )

    parser = DataFrameJobParser()
    api_parser = ApiJobParser()
    jsearch_parser = JSearchJobParser()
    repo = get_job_repository()
    embedding_service = SentenceTransformersEmbeddingAdapter()
    usecase = IngestJobsBatchUseCase(repository=repo, batch_size=200, embedding_service=embedding_service)

    if "loaded_jobs" not in st.session_state:
        st.session_state.loaded_jobs = []
    if "loaded_preview" not in st.session_state:
        st.session_state.loaded_preview = None
    if "loaded_source" not in st.session_state:
        st.session_state.loaded_source = None
    if "loaded_errors" not in st.session_state:
        st.session_state.loaded_errors = []

    if source == "CSV upload":
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded_file is None:
            st.info("Upload a CSV to convert it into jobs and ingest it in batches of 200.")
        else:
            dataframe = pd.read_csv(uploaded_file)
            jobs, errors = parser.to_jobs_with_errors_from_dataframe(dataframe)

            st.session_state.loaded_jobs = jobs
            st.session_state.loaded_preview = dataframe
            st.session_state.loaded_source = "CSV upload"
            st.session_state.loaded_errors = errors

            st.markdown("### Type transitions")
            st.write(f"1. Uploaded file -> `{type(uploaded_file).__name__}`")
            st.write(f"2. Parsed table -> `{type(dataframe).__name__}`")
            st.write(f"3. Domain objects -> `{type(jobs).__name__}`")
            st.write(f"4. Batch size -> `200` jobs")
            if errors:
                st.warning(f"Discarded {len(errors)} row(s) missing required fields, including description.")
                st.table(pd.DataFrame(errors))
    elif source == "JSearch (IT jobs)":
        st.caption(
            "Fetch IT jobs from JSearch (RapidAPI). The free plan is rate-limited "
            "(~200 requests/month, ~10 jobs each), so **each fetch below spends 1 request**. "
            "For bulk collection use `testing/scripts/harvest_jobs_jsearch.py`."
        )
        js_key = st.text_input(
            "RapidAPI key",
            value=os.getenv("JSEARCH_API_KEY", os.getenv("RAPIDAPI_KEY", "")),
            type="password",
            help="x-rapidapi-key for jsearch.p.rapidapi.com. Leave blank to use JSEARCH_API_KEY from the environment.",
        )
        js_query = st.text_input(
            "Search query",
            value="entry level software engineer",
            help="e.g. 'data analyst', 'cybersecurity analyst', 'junior developer'.",
        )
        col_a, col_b = st.columns(2)
        js_location = col_a.text_input("Location", value="United States",
                                       help="City/state/country, or 'remote'.")
        js_pages = col_b.number_input("Pages to fetch (1 page = 1 request = ~10 jobs)",
                                      min_value=1, max_value=5, value=1, step=1)

        if not js_query:
            st.info("Enter a search query to fetch IT jobs from JSearch.")
        elif st.button("Fetch JSearch jobs"):
            query = js_query if js_location.strip().lower() in ("", "remote") else f"{js_query} jobs in {js_location}"
            if js_location.strip().lower() == "remote":
                query = f"{js_query} remote"
            all_records: list[dict] = []
            spent = 0
            remaining = None
            try:
                for page in range(1, int(js_pages) + 1):
                    resp = search_jobs(query, page=page, num_pages=1, api_key=js_key or None)
                    spent += 1
                    remaining = resp.requests_remaining
                    all_records.extend(jsearch_parser.to_normalized_records(resp.payload))
            except Exception as exc:  # noqa: BLE001 - surface API/quota errors in the UI
                st.error(f"JSearch request failed after {spent} request(s): {exc}")
                all_records = all_records  # keep whatever we already got

            records = jsearch_parser.dedupe_by_id(all_records)
            jobs, errors = parser.to_jobs_with_errors_from_records(records)
            st.session_state.loaded_jobs = jobs
            st.session_state.loaded_preview = pd.DataFrame(records)
            st.session_state.loaded_source = "JSearch (IT jobs)"
            st.session_state.loaded_errors = errors

            st.markdown("### Type transitions")
            st.write(f"1. Query -> `{query}`")
            st.write(f"2. Requests spent -> `{spent}` (API quota remaining: `{remaining}`)")
            st.write(f"3. Unique records (deduped by job_id) -> `{len(records)}`")
            st.write(f"4. Valid domain objects -> `{len(jobs)}`")
            st.write("5. Persist batch size on Ingest -> `200` jobs per SQLite write batch")
            if remaining is not None:
                st.info(f"JSearch quota remaining this month: **{remaining}**.")
            if errors:
                st.warning(f"Discarded {len(errors)} row(s) missing required fields, including description.")
                st.table(pd.DataFrame(errors))
    else:
        endpoint = st.text_input("API endpoint", placeholder="https://example.com/api/jobs")
        api_key = st.text_input(
            "API key",
            value=os.getenv("JOB_API_KEY", ""),
            type="password",
            help="Leave blank if the key is already set in your environment.",
        )
        api_job_limit = st.number_input(
            "Number of jobs to load from API",
            min_value=1,
            max_value=500,
            value=int(os.getenv("API_JOB_LIMIT", "500")),
            step=1,
            help="Fetches up to N jobs. Providers such as Arbeitnow return ~100 per page; additional pages are requested automatically.",
        )

        if not endpoint:
            st.info("Enter an API endpoint to import jobs.")
        elif st.button("Fetch API data"):
            limit = int(api_job_limit)
            payload, pages_fetched = fetch_jobs(
                endpoint=endpoint,
                api_key=api_key or None,
                max_jobs=limit,
            )
            records = api_parser.to_records(payload)
            total_raw = len(records)
            jobs, errors = api_parser.to_jobs_with_errors_from_records(records)
            st.session_state.loaded_jobs = jobs
            st.session_state.loaded_preview = pd.DataFrame(records)
            st.session_state.loaded_source = "API endpoint"
            st.session_state.loaded_errors = errors
            st.session_state.api_records_fetched = total_raw
            st.session_state.api_pages_fetched = pages_fetched
            st.session_state.api_job_limit = limit

            st.markdown("### Type transitions")
            st.write("1. Endpoint input -> `str`")
            st.write(f"2. API pages fetched -> `{pages_fetched}`")
            st.write(f"3. Parsed records (after pagination, cap {limit}) -> `{total_raw}`")
            st.write(f"4. Valid domain objects -> `{len(jobs)}`")
            st.write("5. Persist batch size on Ingest -> `200` jobs per SQLite write batch")
            if errors:
                st.warning(f"Discarded {len(errors)} row(s) missing required fields, including description.")
                st.table(pd.DataFrame(errors))

    jobs = st.session_state.loaded_jobs
    preview = st.session_state.loaded_preview

    if jobs:
        loaded_msg = f"Loaded {len(jobs)} jobs from {st.session_state.loaded_source}."
        if st.session_state.get("loaded_source") == "API endpoint":
            fetched = st.session_state.get("api_records_fetched")
            limit = st.session_state.get("api_job_limit")
            pages = st.session_state.get("api_pages_fetched")
            if fetched is not None and limit is not None:
                page_note = f" across {pages} API page(s)" if pages else ""
                loaded_msg += f" Loaded {fetched} record(s){page_note} (limit {limit})."
                if fetched < limit:
                    st.info(
                        f"Only {fetched} jobs were available from the API (requested up to {limit}). "
                        "Try another endpoint or fewer filters if the provider supports more pages."
                    )
        st.success(loaded_msg)
        if preview is not None:
            st.dataframe(preview, use_container_width=True)

    if st.button("Ingest"):
        if not jobs:
            st.warning("No jobs were loaded yet.")
            return

        result = usecase.execute(jobs)
        st.json(result)
        try:
            st.write(f"Total rows in DB: {repo.count()}")
        except Exception:
            st.write("Ingested (count unavailable)")


if __name__ == "__main__":
    run_demo()
