"""Skip manufacturer path templates that 404 on a host.

A single miss is not enough: that SKU may simply not exist. After two
different MPNs 404 the same portable template with no hits, later SKUs on
that host skip the guess so the fetch window goes to search / web results.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from io_utils import atomic_write_text
from sources.page_ok import is_not_found, is_usable_page
from sources.url_patterns import exact_portable_templates

DEAD_PATHS_FILE = Path(__file__).resolve().parents[1] / "data" / "dead_paths.json"
MISS_THRESHOLD = 2

_lock = threading.Lock()
_cache: dict[str, dict[str, dict[str, int]]] | None = None


def _reset_cache() -> None:
    global _cache
    _cache = None


def _read() -> dict[str, dict[str, dict[str, int]]]:
    global _cache
    if _cache is not None:
        return _cache
    if not DEAD_PATHS_FILE.exists():
        _cache = {}
        return _cache
    try:
        payload = json.loads(DEAD_PATHS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        _cache = {}
        return _cache
    cleaned: dict[str, dict[str, dict[str, int]]] = {}
    if isinstance(payload, dict):
        for host, templates in payload.items():
            if not isinstance(templates, dict):
                continue
            bucket: dict[str, dict[str, int]] = {}
            for template, stats in templates.items():
                if not isinstance(stats, dict):
                    continue
                bucket[str(template)] = {
                    "miss": int(stats.get("miss") or 0),
                    "hit": int(stats.get("hit") or 0),
                }
            if bucket:
                cleaned[str(host)] = bucket
    _cache = cleaned
    return _cache


def _write(payload: dict[str, dict[str, dict[str, int]]]) -> None:
    DEAD_PATHS_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        DEAD_PATHS_FILE,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _host_of(template: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(template).netloc or "").lower().removeprefix("www.")


def is_dead_template(template: str) -> bool:
    host = _host_of(template)
    stats = _read().get(host, {}).get(template) or {}
    return int(stats.get("miss") or 0) >= MISS_THRESHOLD and int(stats.get("hit") or 0) == 0


def drop_dead_urls(urls: list[str], mpn: str) -> list[str]:
    kept: list[str] = []
    for url in urls or []:
        templates = exact_portable_templates(url, mpn)
        if templates and any(is_dead_template(item) for item in templates):
            continue
        kept.append(url)
    return kept


def note_outcome(requested: str, mpn: str, status: int, html: str, final_url: str) -> None:
    templates = exact_portable_templates(requested, mpn)
    if not templates:
        return
    if is_not_found(status, html, final_url) or is_not_found(status, html, requested):
        _bump(templates, "miss")
        return
    if is_usable_page(status, html, final_url):
        _bump(templates, "hit")


def _bump(templates: list[str], field: str) -> None:
    global _cache
    with _lock:
        payload = _read()
        changed = False
        for template in templates:
            host = _host_of(template)
            if not host:
                continue
            stats = payload.setdefault(host, {}).setdefault(template, {"miss": 0, "hit": 0})
            stats[field] = int(stats.get(field) or 0) + 1
            changed = True
        if changed:
            try:
                _write(payload)
            except OSError:
                return
        _cache = payload
