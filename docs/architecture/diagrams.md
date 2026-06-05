# Diagrams

Mermaid diagrams of the major flows. (GitHub renders Mermaid in Markdown.)

## End-to-end pipeline

```mermaid
flowchart LR
  subgraph Ingest
    SRC[CSV / generic API / JSearch] --> PARSE[parsers] --> EMB[embed all-MiniLM-L6-v2] --> DB[(SQLite jobs.db)]
  end
  DB --> DASH[Dashboard + role classifier]
  DB --> SEARCH[Job Search: keyword vs semantic]
  DB --> MATCH[Job Matching: cosine]
  MATCH --> AI[AI recommendations LLM]
  RAW[(jsearch_raw + manifest)] --> TRAIN[train_role_classifier.py] --> REG[(model registry)]
  REG --> DASH
  REG --> SEARCH
```

## JSearch harvest (budget-safe)

```mermaid
flowchart TD
  PLAN[query matrix: 22 roles x 12 locations] --> CHK{in manifest?}
  CHK -- yes --> SKIP[skip - no request spent]
  CHK -- no --> REQ[JSearch request]
  REQ --> RAW[write raw JSON to disk FIRST]
  RAW --> MAN[update manifest]
  MAN --> QUOTA{quota / budget left?}
  QUOTA -- yes --> CHK
  QUOTA -- no --> STOP[stop]
  RAW --> INGEST[dedupe by job_id -> embed -> SQLite + master CSV]
```

## Keyword vs semantic search

```mermaid
flowchart LR
  Q[user query] --> KW[TF-IDF vector] --> KWS[cosine vs job TF-IDF] --> KR[keyword results]
  Q --> SE[MiniLM embedding] --> SES[cosine vs job embeddings] --> SR[semantic results]
  KR --> DIFF{set diff}
  SR --> DIFF
  DIFF --> ONLY[semantic-only finds]
```

## Resume matching + AI

```mermaid
flowchart LR
  PDF[resume PDF] --> TXT[pypdf extract] --> RVEC[embed resume]
  RVEC --> COS[cosine vs all job embeddings] --> TOPK[top-k shortlist]
  TOPK --> LLM[OpenAI-compatible LLM] --> REC[resume score + top job recommendations]
```

## MLOps lifecycle

```mermaid
flowchart LR
  ING[ingest new jobs] --> FP{dataset fingerprint changed?}
  FP -- yes --> RT[retrain] --> NV[new model version registered]
  NV --> CI[CI: build + test + train]
  CI --> IMG[build image -> ACR]
  IMG --> DEP[deploy -> Azure Container Apps]
```

## Hexagonal architecture (ports & adapters)

```mermaid
flowchart TB
  subgraph IN[Inbound adapters]
    ST[Streamlit pages]
    APIc[API clients\nArbeitnow · JSearch]
    UP[CSV / PDF parsers]
  end
  subgraph APP[Application · use cases]
    UC1[IngestJobsBatch]
    UC2[SearchJobs]
    UC3[MatchJobsToResume]
    UC4[RecommendJobsWithAI]
    UC5[GetJobDashboard]
  end
  subgraph DOM[Domain]
    E[Job · Resume · Recommendation]
    S[cosine_similarity]
  end
  subgraph PORTS[Ports output]
    P1[[JobRepositoryPort]]
    P2[[EmbeddingServicePort]]
    P3[[JobClassifierPort]]
    P4[[ResumeRecommendationServicePort]]
  end
  subgraph OUT[Outbound adapters]
    A1[SQLite / Postgres repo]
    A2[SentenceTransformers MiniLM]
    A3[sklearn role classifier]
    A4[OpenAI-compatible LLM]
    A5[TF-IDF keyword search]
    A6[structured JSON logging]
  end
  IN --> APP --> DOM
  APP --> PORTS
  P1 --- A1
  P2 --- A2
  P3 --- A3
  P4 --- A4
```

## Deployment topology (Azure)

```mermaid
flowchart TB
  USER[Browser] -->|HTTPS| ING[Container Apps ingress / Envoy]
  subgraph ACA[Container Apps env · cae-resume2job · eastus]
    ING --> BLUE[Revision BLUE\nresume2job--gOLD]
    ING -. 0% .-> GREEN[Revision GREEN\nresume2job--gNEW]
  end
  BLUE -->|DATABASE_URL sslmode=require| PG[(PostgreSQL Flexible Server\nr2j-pg · centralus · db jobs)]
  GREEN --> PG
  BLUE -->|pull| ACR[(ACR r2jacr…azurecr.io\nresume-to-job:sha)]
  GREEN --> ACR
  BLUE --> LAW[(Log Analytics)]
  GREEN --> LAW
  BLUE -->|HTTPS| LLM[Gemini / OpenAI-compatible API]
```

## CI/CD pipeline + blue-green release (sequence)

```mermaid
sequenceDiagram
  participant Dev
  participant GH as GitHub Actions
  participant ACR
  participant ACA as Container App
  Dev->>GH: push to main
  GH->>GH: build-test-train (pytest + train_role_classifier.py)
  Note over GH: gate — only if main & ENABLE_DEPLOY=true
  GH->>ACR: docker build & push :sha + :latest
  GH->>ACA: revision set-mode multiple
  GH->>ACA: update --image :sha --revision-suffix gSHA (GREEN @ 0%)
  ACA->>ACR: pull image
  GH->>ACA: poll runningState until Running
  GH->>ACA: GET green-fqdn /_stcore/health
  alt healthy (200)
    GH->>ACA: traffic set GREEN=100 BLUE=0
    Note over ACA: near-zero-downtime swap; BLUE kept warm
  else unhealthy
    GH->>ACA: revision deactivate GREEN
    Note over ACA: BLUE never lost traffic — release aborted
  end
```

## Blue-green state machine

```mermaid
stateDiagram-v2
  [*] --> Blue100: BLUE serves 100%
  Blue100 --> GreenStaged: deploy GREEN @ 0%
  GreenStaged --> HealthCheck: probe GREEN health
  HealthCheck --> Swapped: 200 → GREEN=100, BLUE=0
  HealthCheck --> Aborted: fail → deactivate GREEN
  Aborted --> Blue100
  Swapped --> [*]: GREEN becomes BLUE; old BLUE warm for rollback
```
