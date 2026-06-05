#!/usr/bin/env python3
"""Harvest IT jobs for grad students from JSearch (RapidAPI) and persist them.

The JSearch free plan is rate-limited (≈200 requests/month, ~10 jobs/request),
so this script is built to **never waste a paid request**:

  * Every API response is written to disk under ``data/jsearch_raw/`` *before*
    anything else. Embedding/DB failures therefore cost zero extra requests.
  * A manifest (``data/jsearch_raw/manifest.json``) records every (query, page)
    already fetched, so re-running the script never re-spends on the same call.
  * A hard budget guard (``--max-requests``) plus the live
    ``x-ratelimit-requests-remaining`` header stop the run before the quota dies.

Pipeline:  fetch (cached) -> dedupe by job_id -> embed -> SQLite + master CSV.

Typical usage:
    # See the plan and how many requests it would spend, WITHOUT calling the API:
    python testing/scripts/harvest_jobs_jsearch.py --dry-run

    # Fetch up to 20 new requests, then ingest everything (set the key first):
    export JSEARCH_API_KEY=...your-rapidapi-key...
    python testing/scripts/harvest_jobs_jsearch.py --max-requests 20

    # Re-build the DB + CSV from the cached raw responses (NO API calls):
    python testing/scripts/harvest_jobs_jsearch.py --ingest-only

Environment:
    JSEARCH_API_KEY / RAPIDAPI_KEY   RapidAPI key for jsearch.p.rapidapi.com
    JOB_DB_PATH                      SQLite DB path (default: data/jobs.db)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# Make ``src`` importable when run as a script from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.adapters.inbound.api_provider.jsearch_client import search_jobs  # noqa: E402
from src.adapters.inbound.api_provider.jsearch_job_parser import (  # noqa: E402
    JSearchJobParser,
)
from src.adapters.inbound.file_upload.dataframe_job_parser import (  # noqa: E402
    DataFrameJobParser,
)
from src.adapters.outbound.embedding.sentence_transformers_adapter import (  # noqa: E402
    SentenceTransformersEmbeddingAdapter,
)
from src.adapters.outbound.persistence.repository_factory import (  # noqa: E402
    get_job_repository,
    job_store_label,
)
from src.application.use_cases.ingest_jobs_batch import (  # noqa: E402
    IngestJobsBatchUseCase,
)

RAW_DIR = REPO_ROOT / "data" / "jsearch_raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"
MASTER_CSV = REPO_ROOT / "data" / "jobs_master.csv"

# --- Query plan: IT roles relevant to IT graduate students -------------------
# Entry-level / new-grad oriented roles across the IT spectrum.
ROLES = [
    "entry level software engineer",
    "junior software developer",
    "new grad software engineer",
    "full stack developer",
    "front end developer",
    "back end developer",
    "data analyst",
    "junior data scientist",
    "data engineer",
    "machine learning engineer",
    "cloud engineer",
    "devops engineer",
    "cybersecurity analyst",
    "information security analyst",
    "IT support specialist",
    "help desk technician",
    "systems administrator",
    "network engineer",
    "QA engineer",
    "business intelligence analyst",
    "database administrator",
    "mobile developer",
]

# "remote" and "United States" are broad/high-yield and are tried first per role.
LOCATIONS = [
    "remote",
    "United States",
    "New York, NY",
    "San Francisco, CA",
    "Seattle, WA",
    "Austin, TX",
    "Chicago, IL",
    "Boston, MA",
    "Atlanta, GA",
    "Dallas, TX",
    "Denver, CO",
    "Los Angeles, CA",
]

# How many pages (10 jobs each) to attempt per (role, location). The harvester
# only advances to page N+1 for a pair once page N has been fetched, so a small
# budget naturally spreads across many pairs (breadth) before going deep.
PAGES_PER_PAIR = 2


def build_query(role: str, location: str) -> str:
    if location.lower() == "remote":
        return f"{role} remote"
    return f"{role} jobs in {location}"


def plan_calls() -> list[dict[str, object]]:
    """Ordered list of intended (query, page) calls.

    Ordering favors breadth: every role is paired with 'remote' and
    'United States' first, then the run deepens city-by-city, then page-by-page.
    """
    calls: list[dict[str, object]] = []
    for page in range(1, PAGES_PER_PAIR + 1):
        for location in LOCATIONS:
            for role in ROLES:
                calls.append(
                    {
                        "role": role,
                        "location": location,
                        "page": page,
                        "query": build_query(role, location),
                    }
                )
    return calls


def call_key(query: str, page: int) -> str:
    return f"{query}::p{page}"


def raw_filename(query: str, page: int) -> str:
    digest = hashlib.sha1(call_key(query, page).encode("utf-8")).hexdigest()[:16]
    return f"{digest}.json"


def load_manifest() -> dict[str, object]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"calls": {}}


def save_manifest(manifest: dict[str, object]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def harvest(max_requests: int, min_remaining: int) -> int:
    """Fetch new (query, page) calls until the request budget is exhausted."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    done: dict[str, object] = manifest.setdefault("calls", {})

    pending = [c for c in plan_calls() if call_key(c["query"], c["page"]) not in done]
    print(f"Plan: {len(plan_calls())} total calls, {len(pending)} not yet fetched.")
    if not pending:
        print("Nothing new to fetch — all planned calls are cached.")
        return 0

    spent = 0
    for call in pending:
        if spent >= max_requests:
            print(f"Reached --max-requests={max_requests}. Stopping.")
            break

        query, page = call["query"], int(call["page"])
        try:
            resp = search_jobs(query, page=page, num_pages=1)
        except Exception as exc:  # noqa: BLE001 - surface and stop, don't crash mid-budget
            print(f"  ! ERROR on {call_key(query, page)}: {exc}")
            print("  Stopping to avoid burning the budget on a failing endpoint.")
            break

        spent += 1
        # Persist the raw response FIRST so the paid data is never lost.
        records = JSearchJobParser().extract_list(resp.payload)
        raw_path = RAW_DIR / raw_filename(query, page)
        raw_path.write_text(json.dumps(resp.payload, ensure_ascii=False))
        done[call_key(query, page)] = {
            "query": query,
            "page": page,
            "role": call["role"],
            "location": call["location"],
            "results": len(records),
            "file": raw_path.name,
        }
        save_manifest(manifest)

        remaining = resp.requests_remaining
        print(
            f"  [{spent}/{max_requests}] {query!r} p{page}: "
            f"{len(records)} jobs | quota remaining: {remaining}"
        )

        if remaining is not None and remaining <= min_remaining:
            print(
                f"  Quota remaining ({remaining}) hit safety floor "
                f"(--min-remaining={min_remaining}). Stopping."
            )
            break

        time.sleep(1.0)  # be polite to the API

    print(f"Harvest done: spent {spent} request(s) this run.")
    return spent


def load_all_raw_records() -> list[dict[str, object]]:
    """Read every cached raw response and return normalized, deduped records."""
    parser = JSearchJobParser()
    full: list[dict[str, object]] = []
    if not RAW_DIR.exists():
        return []
    for path in sorted(RAW_DIR.glob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"  ! skipping unreadable raw file: {path.name}")
            continue
        full.extend(parser.to_full_records(payload))
    deduped = parser.dedupe_by_id(full)
    print(f"Loaded {len(full)} raw records -> {len(deduped)} unique by job_id.")
    return deduped


def write_master_csv(records: list[dict[str, object]]) -> None:
    if not records:
        return
    MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id", "title", "company", "location", "source", "employment_type",
        "is_remote", "city", "state", "country", "salary", "apply_link",
        "publisher", "posted_at_utc", "description",
    ]
    with MASTER_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow(rec)
    print(f"Wrote master CSV: {MASTER_CSV} ({len(records)} unique jobs).")


def ingest(records: list[dict[str, object]], embed: bool) -> None:
    """Embed (optional) and persist deduped records into the app SQLite DB."""
    # Drop records missing required fields (id/title/company/description).
    jobs, errors = DataFrameJobParser().to_jobs_with_errors_from_records(records)
    if errors:
        print(f"  Skipped {len(errors)} record(s) missing required fields.")
    if not jobs:
        print("No valid jobs to ingest.")
        return

    # Persist into the shared store: Postgres when DATABASE_URL is set, else SQLite.
    repo = get_job_repository()
    embedding_service = SentenceTransformersEmbeddingAdapter() if embed else None
    usecase = IngestJobsBatchUseCase(
        repository=repo, batch_size=200, embedding_service=embedding_service
    )
    result = usecase.execute(jobs)
    print(f"Ingested into {job_store_label()}: {result}")
    print(f"Total rows in DB now: {repo.count()} (with embeddings: {repo.count_with_embeddings()}).")
    repo.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-requests", type=int, default=20,
                    help="Hard cap on NEW API requests this run (default: 20).")
    ap.add_argument("--min-remaining", type=int, default=5,
                    help="Stop if the API's remaining-quota header drops to this (default: 5).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show the plan and exit WITHOUT calling the API.")
    ap.add_argument("--ingest-only", action="store_true",
                    help="Skip the API; (re)build DB + CSV from cached raw responses.")
    ap.add_argument("--no-embed", action="store_true",
                    help="Persist without computing embeddings (faster; for testing).")
    args = ap.parse_args()

    if args.dry_run:
        calls = plan_calls()
        manifest = load_manifest()
        done = manifest.get("calls", {})
        pending = [c for c in calls if call_key(c["query"], c["page"]) not in done]
        print(f"Roles: {len(ROLES)}, Locations: {len(LOCATIONS)}, pages/pair: {PAGES_PER_PAIR}")
        print(f"Total planned calls: {len(calls)} | already cached: {len(done)} | pending: {len(pending)}")
        print("First 10 pending queries:")
        for c in pending[:10]:
            print(f"  - {c['query']!r} (page {c['page']})")
        print("\nDry run: no API calls made, 0 requests spent.")
        return 0

    if not args.ingest_only:
        harvest(max_requests=args.max_requests, min_remaining=args.min_remaining)

    records = load_all_raw_records()
    write_master_csv(records)
    ingest(records, embed=not args.no_embed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
