from __future__ import annotations

import json
from collections.abc import Sequence

import psycopg

from src.domain.entities.Job import Job
from src.ports.output.job_repository import JobRepositoryPort


class PostgresJobRepository(JobRepositoryPort):
	"""PostgreSQL-backed repository adapter.

	Mirrors :class:`SQLiteJobRepository` exactly — same table shape, same
	JSON-encoded ``embedding`` column — so the two are drop-in interchangeable
	behind :class:`JobRepositoryPort`. Used for the shared local + cloud database
	so ingested jobs and their embeddings persist across container restarts.

	The DSN is a standard libpq/psycopg connection string, e.g.
	``postgresql://user:pass@host:5432/jobs?sslmode=require``.
	"""

	def __init__(self, dsn: str) -> None:
		self._dsn = dsn
		# autocommit keeps parity with the SQLite adapter's commit-per-write
		# behaviour and avoids leaving idle-in-transaction connections around
		# when Streamlit reruns the script.
		self._conn = psycopg.connect(dsn, autocommit=True)
		self._ensure_table()

	def _ensure_table(self) -> None:
		with self._conn.cursor() as cur:
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS jobs (
					id TEXT PRIMARY KEY,
					title TEXT NOT NULL,
					company TEXT NOT NULL,
					description TEXT,
					location TEXT,
					source TEXT,
					embedding TEXT,
					created_at TIMESTAMPTZ DEFAULT now(),
					updated_at TIMESTAMPTZ DEFAULT now()
				)
				"""
			)

	@staticmethod
	def _embedding_json(job: Job) -> str | None:
		emb = getattr(job, "embedding", None)
		return json.dumps(list(emb)) if emb is not None else None

	def upsert(self, job: Job) -> None:
		self.upsert_many([job])

	def upsert_many(self, jobs: Sequence[Job]) -> None:
		sql = """
		INSERT INTO jobs (id, title, company, description, location, source, embedding, created_at, updated_at)
		VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())
		ON CONFLICT (id) DO UPDATE SET
			title=EXCLUDED.title,
			company=EXCLUDED.company,
			description=EXCLUDED.description,
			location=EXCLUDED.location,
			source=EXCLUDED.source,
			embedding=EXCLUDED.embedding,
			updated_at=now()
		"""
		params = [
			(
				j.id,
				j.title,
				j.company,
				getattr(j, "description", None),
				j.location,
				j.source,
				self._embedding_json(j),
			)
			for j in jobs
		]
		if not params:
			return
		with self._conn.cursor() as cur:
			cur.executemany(sql, params)

	def count(self) -> int:
		with self._conn.cursor() as cur:
			cur.execute("SELECT COUNT(*) FROM jobs")
			row = cur.fetchone()
		return int(row[0]) if row is not None else 0

	def count_with_embeddings(self) -> int:
		with self._conn.cursor() as cur:
			cur.execute(
				"SELECT COUNT(*) FROM jobs WHERE embedding IS NOT NULL AND TRIM(embedding) != ''"
			)
			row = cur.fetchone()
		return int(row[0]) if row is not None else 0

	def find_all(self) -> list[Job]:
		total = self.count()
		return self.find_page(offset=0, limit=total) if total > 0 else []

	def find_page(self, *, offset: int, limit: int) -> list[Job]:
		if limit < 1:
			return []
		with self._conn.cursor() as cur:
			cur.execute(
				"""
				SELECT id, title, company, description, location, source, embedding
				FROM jobs
				ORDER BY updated_at DESC, title ASC, id ASC
				LIMIT %s OFFSET %s
				""",
				(limit, max(offset, 0)),
			)
			rows = cur.fetchall()
		return [self._row_to_job(row) for row in rows]

	@staticmethod
	def _row_to_job(row: tuple) -> Job:
		job_id, title, company, description, location, source, embedding_raw = row
		embedding = None
		if embedding_raw:
			parsed = json.loads(embedding_raw)
			embedding = tuple(float(value) for value in parsed)
		return Job(
			id=job_id,
			title=title,
			company=company,
			description=description or "",
			location=location,
			source=source,
			embedding=embedding,
		)

	def close(self) -> None:
		try:
			self._conn.close()
		except Exception:
			pass
