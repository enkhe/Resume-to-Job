# Architecture Overview

Resume-to-Job follows a **hexagonal (ports & adapters)** architecture. Business rules live in
the domain and application layers and depend only on *ports* (interfaces); concrete technology
(SQLite, Sentence-Transformers, scikit-learn, OpenAI-compatible LLMs, Streamlit) lives in
*adapters* that implement those ports. This keeps the core testable and the infrastructure
swappable.

## Layers

```text
pages/ (Streamlit entrypoints)
  └── adapters/inbound/        streamlit · api_provider · file_upload
        └── application/use_cases/      ingest · match · recommend · search · dashboard
              └── domain/               entities (Job, Resume, Recommendation) · services (similarity)
                    └── ports/output/   job_repository · embedding_service · recommendation_service · job_classifier
                          └── adapters/outbound/   persistence · embedding · llm · ml · search · logging
```

- **Domain** ([src/domain](../../src/domain)) — `Job`, `Resume`, `Recommendation` entities and pure
  services such as `cosine_similarity`. No I/O, no frameworks.
- **Application** ([src/application/use_cases](../../src/application/use_cases)) — orchestrates a single
  task (ingest a batch, match a resume, compare searches, recommend with AI). Depends on ports.
- **Ports** ([src/ports/output](../../src/ports/output)) — `JobRepositoryPort`, `EmbeddingServicePort`,
  `ResumeRecommendationServicePort`, `JobClassifierPort`.
- **Inbound adapters** ([src/adapters/inbound](../../src/adapters/inbound)) — Streamlit pages, the
  JSearch/Arbeitnow API clients, CSV/PDF parsers.
- **Outbound adapters** ([src/adapters/outbound](../../src/adapters/outbound)) — SQLite repository,
  Sentence-Transformers embeddings, the scikit-learn job classifier, the TF-IDF keyword search,
  the OpenAI-compatible LLM client, and structured logging.

## Components

| Concern | Port | Adapter |
|---------|------|---------|
| Persistence | `JobRepositoryPort` | `SQLiteJobRepository` |
| Embeddings | `EmbeddingServicePort` | `SentenceTransformersEmbeddingAdapter` (`all-MiniLM-L6-v2`) |
| AI recommendations | `ResumeRecommendationServicePort` | `OpenAICompatibleRecommendationAdapter` (OpenAI / Gemini) |
| Role classification | `JobClassifierPort` | `SklearnJobClassifierAdapter` (TF-IDF + LogisticRegression) |
| Keyword search | — | `TfidfKeywordSearch` |
| Logging | — | `structured_logging` (JSON lines) |

## End-to-end flow

1. **Ingest** — a source adapter produces normalized records → `Job` entities → embeddings →
   SQLite (`IngestJobsBatchUseCase`).
2. **Classify** — `SklearnJobClassifierAdapter` tags jobs by role category in the Dashboard.
3. **Search** — `SearchJobsUseCase` runs keyword (TF-IDF) and semantic (embedding) retrieval.
4. **Match** — `MatchJobsToResumeUseCase` ranks jobs by cosine similarity to a resume embedding.
5. **Recommend** — `RecommendJobsWithAIUseCase` asks an LLM to score the resume and pick top jobs.
6. **Model Ops** — retrain the classifier into a new registered version.

See [diagrams](diagrams.md) for visual flows and [data model](data-model.md) for schemas.
