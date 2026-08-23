"""Committed manufacturer links from one-SKU-per-brand harvest.

``known_urls.json`` stays the gold-sample seed. This file is the catalog of
pages found for leftover / unmapped brands so a later SKU, or a judge row
on the same part, can skip guessing ``{name}.com/p/{mpn}``.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlparse

from io_utils import atomic_write_text
from sources.finder import is_blocked_url, is_distributor_url, is_search_url
from sources.page_ok import is_error_url

HARVEST_LINKS_FILE = Path(__file__).resolve().parent / "harvest_links.json"
_LOCK = threading.Lock()
_cache: dict[str, list[str]] | None = None


def _reset_cache() -> None:
    global _cache
    _cache = None


def _mpn_key(mpn: str) -> str:
    return (mpn or "").strip()


def url_worth_keeping(url: str) -> bool:
    raw = (url or "").strip()
    if not raw.startswith("http"):
        return False
    if is_blocked_url(raw) or is_error_url(raw) or is_distributor_url(raw):
        return False
    path = (urlparse(raw).path or "/").rstrip("/")
    if path in {"", "/"} and "search" not in raw.lower():
        return False
    return True


def _read() -> dict[str, list[str]]:
    if not HARVEST_LINKS_FILE.exists():
        return {}
    try:
        payload = json.loads(HARVEST_LINKS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for key, value in payload.items():
        mpn = _mpn_key(str(key))
        if not mpn or not isinstance(value, list):
            continue
        urls = []
        for item in value:
            url = str(item or "").strip()
            if url_worth_keeping(url) and url not in urls:
                urls.append(url)
        if urls:
            cleaned[mpn] = urls
    return cleaned


def _payload() -> dict[str, list[str]]:
    global _cache
    if _cache is None:
        _cache = _read()
    return _cache


def urls_for_mpn(mpn: str) -> list[str]:
    key = _mpn_key(mpn)
    if not key:
        return []
    payload = _payload()
    found = list(payload.get(key) or [])
    upper = key.upper()
    if upper != key:
        found.extend(payload.get(upper) or [])
    seen: set[str] = set()
    ordered: list[str] = []
    for url in found:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def remember_urls(mpn: str, urls: list[str]) -> list[str]:
    key = _mpn_key(mpn)
    incoming = [url for url in urls or [] if url_worth_keeping(url)]
    if not key or not incoming:
        return []
    added: list[str] = []
    with _LOCK:
        payload = _read()
        merged = list(payload.get(key) or [])
        for url in incoming:
            if url not in merged:
                merged.append(url)
                added.append(url)
        if added:
            payload[key] = merged
            atomic_write_text(
                HARVEST_LINKS_FILE,
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            )
            global _cache
            _cache = payload
    return added


def remember_harvest_records(records: list[dict]) -> list[str]:
    """Persist usable manufacturer URLs from a harvest run for later SKUs."""
    added: list[str] = []
    for record in records or []:
        mpn = record.get("mpn") or record.get("fetch_mpn") or ""
        urls = []
        if record.get("guess_thin") or int(record.get("items") or 0) < 1:
            continue
        urls = []
        mfr = record.get("mfr_url") or ""
        if mfr and not is_search_url(mfr):
            urls.append(mfr)
        for url in record.get("ref_urls") or []:
            if not url or "{mpn}" in url or is_search_url(url):
                continue
            urls.append(url)
        added.extend(remember_urls(mpn, urls[:8]))
        fetch = record.get("fetch_mpn") or ""
        if fetch and fetch != mpn:
            added.extend(remember_urls(fetch, urls))
    return added
