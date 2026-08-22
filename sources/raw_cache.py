"""Persist fetched manufacturer HTML for offline re-parse.

Bounded by RAW_CACHE_MAX_FILES (LRU eviction by mtime) and
RAW_CACHE_TTL_DAYS (stale entries are ignored on load).
"""

import time
from pathlib import Path

from app.config import RAW_CACHE_DIR, RAW_CACHE_MAX_FILES, RAW_CACHE_TTL_DAYS
from io_utils import atomic_write_text, safe_filename


def _raw_path(mpn: str) -> Path:
    return RAW_CACHE_DIR / f"{safe_filename(mpn)}.html"


def save_raw_html(mpn: str, html: str, url: str) -> Path:
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _raw_path(mpn)
    atomic_write_text(path, f"<!-- source: {url} -->\n{html}", encoding="utf-8")
    _evict()
    return path


def _evict() -> None:
    try:
        files = sorted(RAW_CACHE_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    excess = len(files) - RAW_CACHE_MAX_FILES
    for path in files[:max(0, excess)]:
        try:
            path.unlink()
        except OSError:
            continue


def load_raw_html(mpn: str) -> tuple[str, str] | None:
    path = _raw_path(mpn)
    if not path.exists():
        return None
    try:
        age_days = (time.time() - path.stat().st_mtime) / 86400
    except OSError:
        return None
    if age_days > RAW_CACHE_TTL_DAYS:
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    url = ""
    if text.startswith("<!-- source:"):
        first, _, body = text.partition("-->\n")
        url = first.replace("<!-- source:", "").strip()
        return body, url
    return text, url
