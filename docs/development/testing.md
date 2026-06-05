# Testing & Verification

Two complementary layers: fast unit tests (CI) and runtime verification (manual/UI).

## Unit tests (pytest)
Location: [tests/](../../tests). Fast, offline (no model downloads, no network) — they use a fake
embedding service so they run in ~1.5s.

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

Coverage:
- `cosine_similarity` edge cases.
- JSearch parsing: both `/search` and `/search-v2` envelopes, field mapping, dedup, remote location.
- `TfidfKeywordSearch`: lexical hits, and the empty result on vocabulary mismatch (the "keyword gap").
- `SearchJobsUseCase.compare`: semantic-only vs overlap set logic; semantic ranking order.

These run on every push/PR in [CI](../operations/ci-cd.md).

## Runtime verification (the app actually working)
Unit tests prove pieces; verification proves the **app** works end-to-end through its real surface.
The approach used for this project:

- Drive the running Streamlit app in a headless browser (Playwright) — upload a real resume PDF,
  click *Find Matches* and *Get AI Recommendations*, run the keyword-vs-semantic search, and click
  *Retrain* on Model Ops — capturing screenshots as evidence.
- Confirm KPIs, pagination, model banner, predicted-role column, and the semantic-only highlights.

This catches integration seams (file upload, button reruns, model loading) that unit tests can't.

## Offline pipeline evaluation
For a non-UI metric run over sample fixtures:
```bash
python testing/scripts/pipeline_eval.py            # --run-ai if an LLM key is set
```

## Adding tests
- Keep unit tests **offline and fast** — inject fakes for embeddings/LLM/repository.
- Put new fixtures under `testing/sample_data/`.
- When you add a use case, add a test for its happy path and one failure path.
