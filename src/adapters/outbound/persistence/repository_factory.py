from __future__ import annotations

import os

from src.ports.output.job_repository import JobRepositoryPort


def _normalize_pg_dsn(dsn: str) -> str:
	"""Ensure the Postgres DSN requests SSL.

	Azure Database for PostgreSQL requires TLS. If the caller did not specify an
	``sslmode`` we append ``sslmode=require`` so connections from the container
	(and from a local dev machine) succeed without extra configuration.
	"""
	if "sslmode=" in dsn:
		return dsn
	sep = "&" if "?" in dsn else "?"
	return f"{dsn}{sep}sslmode=require"


def get_job_repository() -> JobRepositoryPort:
	"""Return the configured job repository.

	Selection is environment-driven so the same code runs locally and in the
	cloud against one shared database:

	* ``DATABASE_URL`` (or ``JOB_DATABASE_URL``) set  -> PostgreSQL adapter
	  (the shared, persistent store for local + Azure).
	* otherwise                                       -> SQLite adapter at
	  ``JOB_DB_PATH`` (default ``data/jobs.db``) for offline / no-network use.
	"""
	dsn = os.getenv("DATABASE_URL") or os.getenv("JOB_DATABASE_URL")
	if dsn:
		# Imported lazily so SQLite-only environments don't need psycopg.
		from src.adapters.outbound.persistence.postgres_job_repository import (
			PostgresJobRepository,
		)

		return PostgresJobRepository(_normalize_pg_dsn(dsn))

	from src.adapters.outbound.persistence.sqlite_job_repository import (
		SQLiteJobRepository,
	)

	db_path = os.getenv("JOB_DB_PATH", "data/jobs.db")
	return SQLiteJobRepository(db_path)


def using_postgres() -> bool:
	"""True when a shared Postgres store is configured via env."""
	return bool(os.getenv("DATABASE_URL") or os.getenv("JOB_DATABASE_URL"))


def job_store_available() -> bool:
	"""Whether a job store exists to read from.

	Postgres is assumed reachable when configured (a connection error will
	surface to the caller); SQLite requires the database file to exist so the
	UI can show a helpful "ingest first" message instead of an empty store.
	"""
	if using_postgres():
		return True
	from pathlib import Path

	db_path = os.getenv("JOB_DB_PATH", "data/jobs.db")
	return Path(db_path).exists()


def job_store_label() -> str:
	"""Human-readable name of the active store, for UI captions (no secrets)."""
	return "PostgreSQL (shared)" if using_postgres() else os.getenv("JOB_DB_PATH", "data/jobs.db")


def job_store_cache_key() -> str:
	"""Stable, non-sensitive key identifying the active store (for st.cache)."""
	return "postgres" if using_postgres() else os.getenv("JOB_DB_PATH", "data/jobs.db")
