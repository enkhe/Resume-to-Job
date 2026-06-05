# Job Search — Keyword vs Semantic

The **Job Search** page ([3_Job_Search.py](../../pages/3_Job_Search.py)) runs the same query
through two retrieval methods side-by-side so the difference is visible. This demonstrates *why*
embeddings matter: keyword search fails on vocabulary mismatch, semantic search does not.

## The two methods

| | Keyword (TF-IDF) | Semantic (embeddings) |
|---|---|---|
| Representation | Bag-of-words / bigrams, L2-normalized TF-IDF | 384-dim `all-MiniLM-L6-v2` vector |
| Matches on | **Shared literal terms** | **Meaning** |
| Fails when | Query uses different words than the posting | Rarely (paraphrase-robust) |
| Code | [TfidfKeywordSearch](../../src/adapters/outbound/search/tfidf_keyword_search.py) | [SearchJobsUseCase.semantic_search](../../src/application/use_cases/search_jobs.py) |

Both are orchestrated by `SearchJobsUseCase.compare(query, top_k)`, which returns the keyword
hits, the semantic hits, and the set differences (`semantic_only_ids`, `keyword_only_ids`,
`overlap_ids`).

## Why semantic wins (worked example)

Query: **"keep hackers out of our systems"**

- **Keyword (TF-IDF)** returns weak matches (~0.05) on jobs that happen to contain the words
  *systems* — e.g. *Systems Administrator*, *DBA* — and **misses cybersecurity roles entirely**,
  because those postings say *SIEM, threat detection, SOC, incident response*, not "hackers".
- **Semantic** returns *Cybersecurity Analyst*, *SOC Analyst*, *Information Security Specialist*
  at 0.40+ similarity — the right jobs, found by meaning.

The page surfaces a **"Semantic-only finds"** metric and lists the jobs semantic search found that
keyword search missed. Other illustrative queries: *"teach computers to learn from data"* →
Data Science / ML; *"make our website look good on phones"* → Frontend / Mobile.

## Notes

- TF-IDF rows are L2-normalized, so `linear_kernel` == cosine similarity.
- Keyword results with a zero score (no shared terms) are dropped — that absence is the point of
  the contrast.
- Each result is also tagged with the [role classifier's](../mlops/model-card.md) predicted category.
- The keyword index and embedding model are cached per `(db, job_count)` with
  `st.cache_resource` so repeat queries are fast.
