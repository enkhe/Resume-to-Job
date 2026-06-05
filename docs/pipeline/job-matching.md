# Job Matching

The **Job Matching** page ([4_Job_Matching.py](../../pages/4_Job_Matching.py)) takes a resume PDF
and produces (1) a cosine-similarity shortlist and (2) LLM-generated recommendations for that
shortlist only.

## Step 1 — Upload & parse
The PDF is parsed with `pypdf` and embedded with `all-MiniLM-L6-v2`
([resume_pdf_parser.py](../../src/adapters/inbound/streamlit/resume_pdf_parser.py)),
producing a `Resume(file_name, text, embedding)`.

## Step 2 — Find Matches (cosine)
`MatchJobsToResumeUseCase` ([match_jobs_to_resume.py](../../src/application/use_cases/match_jobs_to_resume.py))
scores every stored job's embedding against the resume embedding and returns the top-k
`RankedJobMatch(job, score)`. Jobs without an embedding are skipped and counted.

Result fields: `matches`, `scored_count`, `skipped_no_embedding`, `total_jobs`.
Emits `match_jobs_to_resume.started` / `.completed` / `.failed` events.

## Step 3 — Get AI Recommendations
`RecommendJobsWithAIUseCase` ([recommend_jobs_with_ai.py](../../src/application/use_cases/recommend_jobs_with_ai.py))
sends the resume text plus **only the shortlisted jobs** to an OpenAI-compatible LLM
([openai_compatible_adapter.py](../../src/adapters/outbound/llm/openai_compatible_adapter.py)).

The model returns strict JSON:

```json
{
  "resume_score": 0-100,
  "resume_feedback": "short paragraph",
  "top_jobs": [{ "job_id": "...", "fit_score": 0-100, "rationale": "..." }]
}
```

Up to 3 jobs are recommended (fewer if the shortlist is smaller). The adapter validates job ids
against the candidate list so the model can't invent jobs.

### Providers
- **OpenAI**: base `https://api.openai.com/v1`, model e.g. `gpt-4o-mini`.
- **Google Gemini** (OpenAI-compat): base `https://generativelanguage.googleapis.com/v1beta/openai`,
  model e.g. `gemini-2.5-flash`. The adapter omits `response_format` for Gemini (it often 500s on it)
  and relies on prompt-enforced JSON.

Keys come from the UI or env (`AI_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY`); base from
`AI_API_BASE`; model from `AI_MODEL`. See [configuration](../operations/configuration.md).

> The AI step is the one external, billable call in the app. Everything else (ingest, embeddings,
> search, classification) runs locally.
