from __future__ import annotations

import pandas as pd
import streamlit as st

from src.adapters.outbound.ml.sklearn_job_classifier_adapter import (
	SklearnJobClassifierAdapter,
)
from src.adapters.outbound.persistence.repository_factory import (
	get_job_repository,
	job_store_label,
)
from src.application.use_cases.get_job_dashboard import (
	DEFAULT_PAGE_SIZE,
	GetJobDashboardUseCase,
)
from src.domain.entities.Job import Job
from src.ports.output.job_repository import JobRepositoryPort


def _load_repository() -> JobRepositoryPort:
	return get_job_repository()


def _truncate(text: str, max_len: int = 120) -> str:
	clean = " ".join(text.split())
	if len(clean) <= max_len:
		return clean
	return clean[: max_len - 3] + "..."


def _jobs_to_rows(
	jobs: tuple[Job, ...],
	predictions: list | None = None,
) -> list[dict[str, object]]:
	rows: list[dict[str, object]] = []
	for index, job in enumerate(jobs):
		row: dict[str, object] = {
			"#": index + 1,
			"id": job.id,
			"title": job.title,
			"company": job.company,
			"location": job.location or "",
			"source": job.source or "",
		}
		if predictions is not None:
			pred = predictions[index] if index < len(predictions) else None
			row["predicted_role"] = pred.category if pred is not None else ""
			row["confidence"] = f"{pred.confidence:.0%}" if pred is not None else ""
		row["embedding"] = "Yes" if job.embedding is not None else "No"
		row["description"] = _truncate(job.description)
		rows.append(row)
	return rows


def _load_classifier() -> SklearnJobClassifierAdapter:
	return SklearnJobClassifierAdapter()


def streamlit_app() -> None:
	st.title("Dashboard")
	st.caption("Pipeline overview and paginated job catalog from SQLite")

	if "dashboard_page" not in st.session_state:
		st.session_state.dashboard_page = 1

	repo = _load_repository()
	use_case = GetJobDashboardUseCase(repository=repo)

	header_col, refresh_col = st.columns([4, 1])
	with refresh_col:
		if st.button("Refresh", use_container_width=True):
			st.session_state.dashboard_page = 1
			st.rerun()

	stats = use_case.get_stats()
	m1, m2, m3 = st.columns(3)
	m1.metric("Total jobs", stats.total_jobs)
	m2.metric("With embeddings", stats.jobs_with_embeddings)
	m3.metric("Missing embeddings", stats.jobs_without_embeddings)

	with header_col:
		st.caption(f"Database: `{job_store_label()}`")

	# Owned ML model: job-role classifier (trained via ml/train_role_classifier.py).
	classifier = _load_classifier()
	if classifier.is_ready():
		acc = classifier.metrics.get("accuracy")
		n = classifier.metadata.get("n_samples")
		classes = len(classifier.metadata.get("classes", []))
		acc_txt = f"{acc:.0%} accuracy" if isinstance(acc, (int, float)) else "trained"
		st.caption(
			f"🧠 Role classifier **{classifier.version}** — {acc_txt}, "
			f"{classes} categories, trained on {n} jobs. Predictions shown in the table below."
		)
	else:
		st.caption(
			"🧠 Role classifier: no trained model found. "
			"Run `python ml/train_role_classifier.py` to generate one."
		)

	if stats.total_jobs == 0:
		st.warning("No jobs in the database yet. Ingest jobs on the Data Ingestion page.")
		repo.close()
		return

	# Category mix across the whole corpus, predicted by the ML model.
	if classifier.is_ready():
		all_jobs = repo.find_page(offset=0, limit=stats.total_jobs)
		preds = classifier.predict([f"{j.title}. {j.description}" for j in all_jobs])
		counts = pd.Series([p.category for p in preds]).value_counts()
		st.markdown("### Role-category mix (model-predicted)")
		st.caption("Every job in the database classified by the role model — a live view of your corpus.")
		st.bar_chart(counts, horizontal=True)

	page_data = use_case.get_page(st.session_state.dashboard_page, page_size=DEFAULT_PAGE_SIZE)
	st.session_state.dashboard_page = page_data.page

	st.markdown("### Jobs")
	st.caption(
		f"Showing page **{page_data.page}** of **{page_data.total_pages}** "
		f"({page_data.page_size} jobs per page, {page_data.total_jobs} total)"
	)

	predictions = None
	if classifier.is_ready() and page_data.jobs:
		texts = [f"{job.title}. {job.description}" for job in page_data.jobs]
		predictions = classifier.predict(texts)

	st.dataframe(
		pd.DataFrame(_jobs_to_rows(page_data.jobs, predictions)),
		use_container_width=True,
		hide_index=True,
	)

	nav_prev, nav_info, nav_next = st.columns([1, 2, 1])
	with nav_prev:
		if st.button(
			"Previous page",
			disabled=page_data.page <= 1,
			use_container_width=True,
			key="dashboard_prev",
		):
			st.session_state.dashboard_page = page_data.page - 1
			st.rerun()
	with nav_info:
		st.write(f"Page {page_data.page} / {page_data.total_pages}")
	with nav_next:
		if st.button(
			"Next page",
			disabled=page_data.page >= page_data.total_pages,
			use_container_width=True,
			key="dashboard_next",
		):
			st.session_state.dashboard_page = page_data.page + 1
			st.rerun()

	repo.close()
