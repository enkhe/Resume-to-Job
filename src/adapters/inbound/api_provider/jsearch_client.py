from __future__ import annotations

import os
from dataclasses import dataclass

import requests

JSEARCH_HOST = "jsearch.p.rapidapi.com"
JSEARCH_SEARCH_URL = f"https://{JSEARCH_HOST}/search"


@dataclass(frozen=True, slots=True)
class JSearchResponse:
    """One JSearch page result plus quota bookkeeping from response headers."""

    payload: object
    status_code: int
    requests_limit: int | None
    requests_remaining: int | None


def _int_header(headers, name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_api_key(api_key: str | None = None) -> str | None:
    return api_key or os.getenv("JSEARCH_API_KEY") or os.getenv("RAPIDAPI_KEY")


def search_jobs(
    query: str,
    *,
    page: int = 1,
    num_pages: int = 1,
    country: str = "us",
    date_posted: str = "all",
    api_key: str | None = None,
    host: str = JSEARCH_HOST,
    timeout: int = 60,
) -> JSearchResponse:
    """Call the JSearch ``/search`` endpoint for a single query/page.

    NOTE on quota: each request returns up to ~10 jobs. ``num_pages`` > 1 is
    billed by JSearch as multiple requests, so the harvester keeps ``num_pages=1``
    and walks pages explicitly to keep an exact 1-call-per-request accounting.
    """
    resolved_key = resolve_api_key(api_key)
    if not resolved_key:
        raise ValueError(
            "No JSearch API key. Set JSEARCH_API_KEY (or RAPIDAPI_KEY), "
            "or pass api_key explicitly."
        )

    headers = {"x-rapidapi-key": resolved_key, "x-rapidapi-host": host}
    params = {
        "query": query,
        "page": str(page),
        "num_pages": str(num_pages),
        "country": country,
        "date_posted": date_posted,
    }
    response = requests.get(
        JSEARCH_SEARCH_URL, headers=headers, params=params, timeout=timeout
    )
    response.raise_for_status()
    return JSearchResponse(
        payload=response.json(),
        status_code=response.status_code,
        requests_limit=_int_header(response.headers, "x-ratelimit-requests-limit"),
        requests_remaining=_int_header(
            response.headers, "x-ratelimit-requests-remaining"
        ),
    )
