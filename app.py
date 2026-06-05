import os

import streamlit as st

from src.adapters.outbound.logging.structured_logging import configure_logging

configure_logging()
APP_VERSION = os.getenv("APP_VERSION", "dev")

st.set_page_config(
	page_title="Resume to Job 2.0",
	page_icon="🎯",
	layout="wide",
)

st.title("🎯 Resume to Job")
st.caption(
	f"Version {APP_VERSION} · job ingestion · keyword vs semantic search · "
	"resume matching · AI recommendations · an owned, retrainable ML model"
)


# --- Live pipeline status -----------------------------------------------------
def _job_stats() -> tuple[int, int]:
	try:
		from src.adapters.outbound.persistence.repository_factory import (
			get_job_repository,
			job_store_available,
		)

		if not job_store_available():
			return 0, 0
		repo = get_job_repository()
		total, emb = repo.count(), repo.count_with_embeddings()
		repo.close()
		return total, emb
	except Exception:
		return 0, 0


def _model_status() -> str:
	try:
		from src.adapters.outbound.ml.sklearn_job_classifier_adapter import (
			SklearnJobClassifierAdapter,
		)

		clf = SklearnJobClassifierAdapter()
		if not clf.is_ready():
			return "not trained"
		acc = clf.metrics.get("accuracy")
		acc_txt = f"{acc:.0%}" if isinstance(acc, (int, float)) else "trained"
		return f"{clf.version} ({acc_txt} acc)"
	except Exception:
		return "unavailable"


total_jobs, jobs_with_emb = _job_stats()
m1, m2, m3 = st.columns(3)
m1.metric("Jobs in database", total_jobs)
m2.metric("With embeddings", jobs_with_emb)
m3.metric("Role-classifier model", _model_status())

st.markdown(
	"""
	### Workflow
	1. **Data Ingestion** — load jobs from CSV, a generic API, or **JSearch** (IT jobs); embeddings stored in SQLite.
	2. **Dashboard** — review the catalog and see each job auto-tagged by the **ML role classifier**.
	3. **Job Search** — compare **keyword (TF-IDF)** vs **semantic (embeddings)** retrieval on the same query.
	4. **Job Matching** — upload a resume PDF, rank jobs by cosine similarity, then get **AI recommendations**.
	5. **Model Ops** — view the model registry/metrics and **retrain** to produce a new versioned model.
	"""
)

st.info(
	"This is an **MLOps** project: ingesting new job data lets you retrain the classifier into a new "
	"versioned artifact — the trigger for the automated build/deploy pipeline. "
	"Run locally with `streamlit run app.py` or as a container — see [DEPLOYMENT.md](DEPLOYMENT.md)."
)
