from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from src.adapters.inbound.streamlit.resume_pdf_parser import parse_resume_pdf
from src.adapters.outbound.embedding.sentence_transformers_adapter import (
	SentenceTransformersEmbeddingAdapter,
)
from src.adapters.outbound.llm.openai_compatible_adapter import OpenAICompatibleRecommendationAdapter
from src.adapters.outbound.persistence.repository_factory import get_job_repository
from src.application.use_cases.match_jobs_to_resume import (
	MatchJobsToResumeUseCase,
	RankedJobMatch,
)
from src.application.use_cases.recommend_jobs_with_ai import RecommendJobsWithAIUseCase
from src.domain.entities.Job import Job
from src.domain.entities.Recommendation import ResumeRecommendation
from src.domain.entities.Resume import Resume
from src.ports.output.job_repository import JobRepositoryPort


def _load_repository() -> JobRepositoryPort:
	return get_job_repository()


def _parse_uploaded_resume(uploaded_pdf) -> Resume | None:
	embedding_service = SentenceTransformersEmbeddingAdapter()
	try:
		return parse_resume_pdf(uploaded_pdf, embedding_service=embedding_service)
	except Exception as exc:
		st.error(f"Could not extract text from the PDF: {exc}")
		return None


def _jobs_from_match_result(result: dict[str, object] | None) -> list[Job]:
	if not result or not result.get("ok"):
		return []
	matches = result.get("matches", [])
	return [
		match.job
		for match in matches
		if isinstance(match, RankedJobMatch)
	]


def _has_filtered_matches(match_result: dict[str, object] | None) -> bool:
	return len(_jobs_from_match_result(match_result)) > 0


def _show_match_results(result: dict[str, object]) -> None:
	if not result.get("ok"):
		st.error(str(result.get("message", "Matching failed.")))
		return

	matches = result.get("matches", [])
	scored_count = int(result.get("scored_count", 0))
	skipped = int(result.get("skipped_no_embedding", 0))
	total_jobs = int(result.get("total_jobs", 0))

	if scored_count == 0:
		st.warning(
			str(
				result.get(
					"message",
					"No jobs with embeddings found. Ingest jobs on the Data Ingestion page first.",
				)
			)
		)
		if total_jobs > 0:
			st.caption(f"{total_jobs} job(s) in the database, {skipped} without embeddings.")
		return

	st.success(f"Showing {len(matches)} top match(es) from {scored_count} scored job(s).")
	if skipped:
		st.caption(f"Skipped {skipped} job(s) without stored embeddings.")
	st.caption("These filtered jobs are passed to AI when you click Get AI Recommendations.")

	rows = [
		{
			"rank": index + 1,
			"score": round(match.score, 4),
			"id": match.job.id,
			"title": match.job.title,
			"company": match.job.company,
			"location": match.job.location or "",
		}
		for index, match in enumerate(matches)
		if isinstance(match, RankedJobMatch)
	]
	st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _show_ai_recommendations(result: dict[str, object]) -> None:
	if not result.get("ok"):
		st.error(str(result.get("message", "AI recommendation failed.")))
		return

	recommendation = result.get("recommendation")
	if not isinstance(recommendation, ResumeRecommendation):
		st.error("AI recommendation payload is invalid.")
		return

	candidate_count = int(result.get("candidate_count", 0))
	st.caption(
		f"AI reviewed {candidate_count} filtered job(s) from your latest Find Matches results."
	)

	st.metric("Resume score", f"{recommendation.resume_score:.0f} / 100")
	st.markdown(recommendation.resume_feedback)

	job_count = len(recommendation.top_jobs)
	heading = "Top job to apply to" if job_count == 1 else f"Top {job_count} jobs to apply to"
	st.markdown(f"### {heading}")
	for index, job in enumerate(recommendation.top_jobs, start=1):
		with st.container(border=True):
			st.markdown(f"**#{index} — {job.title}** at **{job.company}**")
			st.caption(f"Job ID: {job.job_id}")
			st.write(f"Fit score: {job.fit_score:.0f} / 100")
			st.write(job.rationale)


def streamlit_app() -> None:
	"""Inbound adapter for the Job Matching page."""
	st.title("Job Matching")
	st.caption(
		"Demo - Upload a resume, filter jobs with cosine similarity, then get an AI score and recommendations "
		"for those filtered jobs only"
	)

	uploaded_pdf = st.file_uploader("Upload PDF resume", type=["pdf"])
	top_k = st.slider("Number of cosine matches to show", min_value=1, max_value=50, value=10)

	with st.expander("AI API settings", expanded=False):
		default_base = os.getenv(
			"AI_API_BASE",
			os.getenv(
				"GEMINI_API_BASE",
				"https://api.openai.com/v1",
			),
		)
		default_model = os.getenv("AI_MODEL", os.getenv("GEMINI_MODEL", "gpt-4o-mini"))
		api_base = st.text_input(
			"API base URL",
			value=default_base,
			help="OpenAI-compatible base URL (no /chat/completions suffix).",
		)
		api_key = st.text_input(
			"API key",
			value=os.getenv(
				"AI_API_KEY",
				os.getenv("GEMINI_API_KEY", os.getenv("OPENAI_API_KEY", "")),
			),
			type="password",
			help="Google AI Studio: create a key at aistudio.google.com/apikey",
		)
		model = st.text_input("Model", value=default_model)
		st.caption(
			"**Google AI Studio:** base "
			"`https://generativelanguage.googleapis.com/v1beta/openai`, "
			"model e.g. `gemini-2.0-flash` or `gemini-2.5-flash`. "
			"See [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)."
		)

	if uploaded_pdf is None:
		st.info("Upload a PDF resume to continue.")
		return

	if (
		st.session_state.get("resume_file_name") != uploaded_pdf.name
		or st.session_state.get("resume_bytes") != uploaded_pdf.getvalue()
	):
		resume = _parse_uploaded_resume(uploaded_pdf)
		if resume is None:
			return
		st.session_state.resume = resume
		st.session_state.resume_file_name = uploaded_pdf.name
		st.session_state.resume_bytes = uploaded_pdf.getvalue()
		st.session_state.match_result = None
		st.session_state.ai_result = None

	resume: Resume | None = st.session_state.get("resume")
	if resume is None:
		st.warning("Could not load a parsed resume. Re-upload the PDF.")
		return

	st.success(f"Uploaded: {resume.file_name}")
	st.text_area("Extracted resume text", value=resume.text, height=300, disabled=True)
	if resume.embedding is not None:
		st.caption(f"Embedding size: {len(resume.embedding)}")
	else:
		st.warning("No embedding was generated. Find Matches requires a readable PDF with text.")

	col_cosine, col_ai = st.columns(2)
	with col_cosine:
		find_matches = st.button(
			"Find Matches",
			type="primary",
			disabled=resume.embedding is None,
			use_container_width=True,
		)

	if find_matches:
		repo = _load_repository()
		use_case = MatchJobsToResumeUseCase(repository=repo)
		st.session_state.match_result = use_case.execute(resume, top_k=top_k)
		st.session_state.ai_result = None

	# Compute after Find Matches handler so the AI button reflects this run's results.
	match_result = st.session_state.get("match_result")
	filtered_jobs = _jobs_from_match_result(match_result)
	can_run_ai = _has_filtered_matches(match_result)

	with col_ai:
		get_ai = st.button(
			"Get AI Recommendations",
			type="secondary",
			disabled=not can_run_ai,
			use_container_width=True,
			help="Run Find Matches first to filter which jobs the AI should review.",
		)

	if get_ai:
		if not api_key:
			st.error("Enter an AI API key in the settings expander or set AI_API_KEY / OPENAI_API_KEY.")
		elif not can_run_ai:
			st.warning("Run Find Matches first so the AI has filtered jobs to review.")
		else:
			ai_service = OpenAICompatibleRecommendationAdapter(
				api_base=api_base or None,
				api_key=api_key,
				model=model or None,
			)
			use_case = RecommendJobsWithAIUseCase(recommendation_service=ai_service)
			with st.spinner(f"Calling AI endpoint for {len(filtered_jobs)} filtered job(s)…"):
				st.session_state.ai_result = use_case.execute(resume, filtered_jobs)

	if not can_run_ai and resume.embedding is not None:
		st.info("Step 1: click **Find Matches**. Step 2: click **Get AI Recommendations** on those results.")

	if st.session_state.get("match_result") is not None:
		st.markdown("### Cosine similarity matches")
		_show_match_results(st.session_state.match_result)

	if st.session_state.get("ai_result") is not None:
		st.markdown("### AI recommendations")
		_show_ai_recommendations(st.session_state.ai_result)
