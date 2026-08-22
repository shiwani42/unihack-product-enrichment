"""Optional shared URL memory across Vercel visitors.

Needs an Upstash Redis REST token (or Vercel Blob token) in env. No token
means a no-op: the app keeps using committed seeds + browser overlay.
Store failures never fail enrichment.
"""

from __future__ import annotations

import json
import os
from urllib.parse import quote

import httpx

SHARED_KEY = "unilog:url_memory"
BLOB_PATHNAME = "unilog-url-memory.json"
MAX_BYTES = 900_000
TIMEOUT = httpx.Timeout(connect=2.0, read=2.5, write=2.5, pool=2.0)


def _upstash_url() -> str:
    return (os.environ.get("UPSTASH_REDIS_REST_URL") or "").rstrip("/")


def _upstash_token() -> str:
    return os.environ.get("UPSTASH_REDIS_REST_TOKEN") or ""


def _blob_token() -> str:
    return os.environ.get("BLOB_READ_WRITE_TOKEN") or ""


def configured() -> bool:
    if os.environ.get("UNILOG_SHARED_MEMORY", "1").strip().lower() in {"0", "false", "no"}:
        return False
    return bool((_upstash_url() and _upstash_token()) or _blob_token())


def merge_memory(base: dict | None, overlay: dict | None) -> dict:
    """Union host intelligence. Overlay wins for the same MPN / search_engine."""
    left = base if isinstance(base, dict) else {}
    right = overlay if isinstance(overlay, dict) else {}
    known: dict[str, list] = {}
    for source in (left.get("known_urls"), right.get("known_urls")):
        if not isinstance(source, dict):
            continue
        for mpn, urls in source.items():
            key = str(mpn)
            bucket = known.setdefault(key, [])
            for url in urls if isinstance(urls, list) else []:
                if url and url not in bucket:
                    bucket.append(url)
    paths: dict[str, list] = {}
    for source in (left.get("search_paths"), right.get("search_paths")):
        if not isinstance(source, dict):
            continue
        for host, templates in source.items():
            key = str(host)
            bucket = paths.setdefault(key, [])
            for template in templates if isinstance(templates, list) else []:
                if template and template not in bucket:
                    bucket.append(template)
    dead: dict = {}
    for source in (left.get("dead_paths"), right.get("dead_paths")):
        if isinstance(source, dict):
            dead.update(source)
    engine = right.get("search_engine") or left.get("search_engine")
    return {
        "known_urls": known,
        "search_paths": paths,
        "dead_paths": dead,
        "search_engine": engine if isinstance(engine, str) else None,
    }


def _trim(payload: dict) -> dict:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(raw.encode("utf-8")) <= MAX_BYTES:
        return payload
    known = dict(payload.get("known_urls") or {})
    keys = list(known)
    while keys and len(json.dumps({**payload, "known_urls": known}, separators=(",", ":")).encode("utf-8")) > MAX_BYTES:
        known.pop(keys.pop(0), None)
    trimmed = dict(payload)
    trimmed["known_urls"] = known
    return trimmed


def _upstash_get() -> dict | None:
    url = f"{_upstash_url()}/get/{quote(SHARED_KEY, safe='')}"
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {_upstash_token()}"},
        timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        return None
    result = response.json().get("result")
    if not result:
        return None
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        data = json.loads(result)
        return data if isinstance(data, dict) else None
    return None


def _upstash_set(payload: dict) -> bool:
    response = httpx.post(
        _upstash_url(),
        headers={"Authorization": f"Bearer {_upstash_token()}", "Content-Type": "application/json"},
        json=["SET", SHARED_KEY, json.dumps(payload, separators=(",", ":"), ensure_ascii=False)],
        timeout=TIMEOUT,
    )
    return response.status_code < 400


def _blob_get() -> dict | None:
    token = _blob_token()
    url = (os.environ.get("UNILOG_BLOB_MEMORY_URL") or "").strip()
    if not url:
        return None
    response = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if response.status_code >= 400:
        return None
    data = response.json()
    return data if isinstance(data, dict) else None


def _blob_set(payload: dict) -> bool:
    token = _blob_token()
    response = httpx.put(
        f"https://blob.vercel-storage.com/{BLOB_PATHNAME}",
        headers={
            "Authorization": f"Bearer {token}",
            "x-content-type": "application/json",
            "x-add-random-suffix": "false",
        },
        content=json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        return False
    try:
        url = response.json().get("url")
    except (json.JSONDecodeError, AttributeError):
        url = ""
    if url:
        os.environ["UNILOG_BLOB_MEMORY_URL"] = str(url)
    return True


def load_shared() -> dict | None:
    if not configured():
        return None
    try:
        if _upstash_url() and _upstash_token():
            return _upstash_get()
        return _blob_get()
    except (httpx.HTTPError, json.JSONDecodeError, OSError, ValueError):
        return None


def save_shared(payload: dict | None) -> bool:
    if not configured() or not isinstance(payload, dict):
        return False
    body = _trim(payload)
    try:
        if _upstash_url() and _upstash_token():
            return _upstash_set(body)
        return _blob_set(body)
    except (httpx.HTTPError, OSError, ValueError):
        return False
