from __future__ import annotations

from collections.abc import Sequence


class JSearchJobParser:
    """Convert JSearch (RapidAPI) job records into the app's normalized record shape.

    JSearch returns records under ``data`` with fields such as ``job_id``,
    ``job_title``, ``employer_name``, ``job_description``, ``job_city`` etc.
    We map those to the ``{id, title, company, description, location, source}``
    shape expected by ``DataFrameJobParser`` / ``IngestJobsBatchUseCase``.

    ``to_full_records`` additionally preserves apply link, salary and employment
    type so the harvested data can be exported to CSV without losing information
    (the core ``Job`` entity only carries the normalized fields).
    """

    DEFAULT_SOURCE = "jsearch"

    def extract_list(self, payload: object) -> list[dict[str, object]]:
        """Return the list of raw job dicts from a JSearch JSON payload.

        Handles both endpoint envelopes:
          * ``/search``    -> ``{"data": [ ...jobs... ]}``
          * ``/search-v2`` -> ``{"data": {"jobs": [ ...jobs... ], "cursor": ...}}``
        """
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
            if isinstance(data, dict):
                jobs = data.get("jobs")
                if isinstance(jobs, list):
                    return [r for r in jobs if isinstance(r, dict)]
            # Some responses put jobs at the top level.
            jobs = payload.get("jobs")
            if isinstance(jobs, list):
                return [r for r in jobs if isinstance(r, dict)]
        return []

    def _location(self, rec: dict[str, object]) -> str | None:
        if rec.get("job_is_remote") is True:
            return "Remote"
        city = (rec.get("job_city") or "").strip() if isinstance(rec.get("job_city"), str) else ""
        state = (rec.get("job_state") or "").strip() if isinstance(rec.get("job_state"), str) else ""
        if city and state:
            return f"{city}, {state}"
        if city:
            return city
        if state:
            return state
        loc = rec.get("job_location")
        if isinstance(loc, str) and loc.strip():
            return loc.strip()
        country = rec.get("job_country")
        if isinstance(country, str) and country.strip():
            return country.strip()
        return None

    def to_normalized_records(self, payload: object) -> list[dict[str, object]]:
        """Map JSearch records to the normalized ingestion record shape."""
        records: list[dict[str, object]] = []
        for rec in self.extract_list(payload):
            records.append(
                {
                    "id": rec.get("job_id"),
                    "title": rec.get("job_title"),
                    "company": rec.get("employer_name"),
                    "description": rec.get("job_description"),
                    "location": self._location(rec),
                    "source": self.DEFAULT_SOURCE,
                }
            )
        return records

    def to_full_records(self, payload: object) -> list[dict[str, object]]:
        """Map JSearch records, keeping extra fields useful for CSV export."""
        records: list[dict[str, object]] = []
        for rec in self.extract_list(payload):
            records.append(
                {
                    "id": rec.get("job_id"),
                    "title": rec.get("job_title"),
                    "company": rec.get("employer_name"),
                    "description": rec.get("job_description"),
                    "location": self._location(rec),
                    "source": self.DEFAULT_SOURCE,
                    "employment_type": rec.get("job_employment_type"),
                    "is_remote": rec.get("job_is_remote"),
                    "city": rec.get("job_city"),
                    "state": rec.get("job_state"),
                    "country": rec.get("job_country"),
                    "salary": rec.get("job_salary_string") or rec.get("job_salary"),
                    "apply_link": rec.get("job_apply_link"),
                    "publisher": rec.get("job_publisher"),
                    "posted_at_utc": rec.get("job_posted_at_datetime_utc"),
                }
            )
        return records

    def dedupe_by_id(
        self, records: Sequence[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Keep the first record per ``id`` (JSearch ``job_id`` is unique)."""
        seen: set[str] = set()
        unique: list[dict[str, object]] = []
        for rec in records:
            job_id = rec.get("id")
            if not isinstance(job_id, str) or not job_id.strip():
                continue
            if job_id in seen:
                continue
            seen.add(job_id)
            unique.append(rec)
        return unique
