#!/usr/bin/env python
"""One-shot migration: copy all jobs (incl. embeddings) from SQLite into Postgres.

Reads from the local SQLite database and writes into the shared Postgres store so
the cloud app sees the same catalog that was built locally.

Usage:
    DATABASE_URL='postgresql://user:pass@host:5432/jobs?sslmode=require' \
    JOB_DB_PATH='data/jobs.db' \
    python testing/scripts/migrate_sqlite_to_postgres.py

Idempotent: rows are upserted by primary key, so re-running is safe.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.adapters.outbound.persistence.postgres_job_repository import (  # noqa: E402
	PostgresJobRepository,
)
from src.adapters.outbound.persistence.repository_factory import (  # noqa: E402
	_normalize_pg_dsn,
)
from src.adapters.outbound.persistence.sqlite_job_repository import (  # noqa: E402
	SQLiteJobRepository,
)


def main() -> int:
	dsn = os.getenv("DATABASE_URL") or os.getenv("JOB_DATABASE_URL")
	if not dsn:
		print("ERROR: set DATABASE_URL to the target Postgres DSN", file=sys.stderr)
		return 2
	src_path = os.getenv("JOB_DB_PATH", str(REPO_ROOT / "data" / "jobs.db"))
	if not Path(src_path).exists():
		print(f"ERROR: source SQLite DB not found: {src_path}", file=sys.stderr)
		return 2

	print(f"Source SQLite : {src_path}")
	src = SQLiteJobRepository(src_path)
	jobs = src.find_all()
	with_emb = sum(1 for j in jobs if j.embedding is not None)
	print(f"Read {len(jobs)} jobs ({with_emb} with embeddings)")

	dst = PostgresJobRepository(_normalize_pg_dsn(dsn))
	# Batch the upsert to keep memory and round-trips reasonable.
	BATCH = 200
	for i in range(0, len(jobs), BATCH):
		chunk = jobs[i : i + BATCH]
		dst.upsert_many(chunk)
		print(f"  upserted {min(i + BATCH, len(jobs))}/{len(jobs)}")

	total = dst.count()
	total_emb = dst.count_with_embeddings()
	print(f"Postgres now has {total} jobs ({total_emb} with embeddings)")
	src.close()
	dst.close()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
