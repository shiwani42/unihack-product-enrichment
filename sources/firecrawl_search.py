"""Firecrawl web search — discover manufacturer pages without scraping SERPs.

Uses POST https://api.firecrawl.dev/v2/search. Requires FIRECRAWL_API_KEY:
keyless calls are rejected with 403 from typical home/cloud IPs and only
add latency. A process-wide circuit breaker skips Firecrawl after the first
hard failure so enrichment does not burn the search budget.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
# Keep tight: a hung keyless call used to eat the whole SEARCH_BUDGET.
FIRECRAWL_TIMEOUT = httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=2.0)

_circuit_open = False
_circuit_reason = ""


def reset_firecrawl_circuit() -> None:
    global _circuit_open, _circuit_reason
    _circuit_open = False
    _circuit_reason = ""


def firecrawl_circuit_open() -> bool:
    return _circuit_open


def _trip_circuit(reason: str) -> None:
    global _circuit_open, _circuit_reason
    _circuit_open = True
    _circuit_reason = reason


def _api_key() -> str:
    return (
        os.environ.get("FIRECRAWL_API_KEY", "").strip()
        or os.environ.get("FIRECRAWL_APIKEY", "").strip()
    )


def firecrawl_has_api_key() -> bool:
    return bool(_api_key())


def firecrawl_enabled() -> bool:
    if os.environ.get("UNILOG_FIRECRAWL", "1").strip().lower() in {"0", "false", "no"}:
        return False
    if _circuit_open:
        return False
    # Keyless returns 403 "suspicious IP" from home and cloud; skip unless keyed.
    if not _api_key():
        return False
    return True


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def parse_firecrawl_urls(payload: Any) -> list[str]:
    """Extract http(s) result URLs from a Firecrawl /v2/search JSON body."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload)
    urls: list[str] = []

    def _keep(url: str) -> None:
        text = (url or "").strip()
        if text.startswith("http") and text not in urls:
            urls.append(text)

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                _keep(str(item.get("url") or item.get("link") or ""))
            elif isinstance(item, str):
                _keep(item)
        return urls

    if isinstance(data, dict):
        for key in ("web", "news", "images", "results"):
            bucket = data.get(key)
            if not isinstance(bucket, list):
                continue
            for item in bucket:
                if isinstance(item, dict):
                    _keep(str(item.get("url") or item.get("link") or item.get("imageUrl") or ""))
                elif isinstance(item, str):
                    _keep(item)
        if not urls:
            _keep(str(data.get("url") or ""))
    return urls


async def firecrawl_search_urls(query: str, limit: int = 8) -> list[str]:
    """Firecrawl search. Returns [] on disable, error, or empty results."""
    if not firecrawl_enabled() or not (query or "").strip():
        return []
    body = {
        "query": query.strip()[:500],
        "limit": max(1, min(int(limit or 8), 10)),
        "sources": [{"type": "web"}],
    }
    try:
        async with httpx.AsyncClient(timeout=FIRECRAWL_TIMEOUT, follow_redirects=True) as client:
            response = await client.post(FIRECRAWL_SEARCH_URL, headers=_headers(), json=body)
    except (httpx.HTTPError, OSError):
        _trip_circuit("network")
        return []
    if response.status_code in (401, 402, 403, 429):
        _trip_circuit(f"http_{response.status_code}")
        return []
    if response.status_code >= 400:
        _trip_circuit(f"http_{response.status_code}")
        return []
    try:
        payload = response.json()
    except ValueError:
        _trip_circuit("bad_json")
        return []
    if isinstance(payload, dict) and payload.get("success") is False:
        _trip_circuit("api_rejected")
        return []
    return parse_firecrawl_urls(payload)[: max(1, min(int(limit or 8), 10))]
