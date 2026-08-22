"""Durable per-SKU product URLs discovered by live search.

Two layers share the work of searching the input set:

* ``known_urls.json`` — exact pages for that part (including SEO-slug PDPs
  that cannot be rebuilt for a different SKU).
* ``search_paths.json`` — host templates with ``{mpn}``. Finding one
  Frigidaire owner-center page, or one Southwire ``/p/{sku}`` page, teaches
  the host so a judge's unseen part on the same brand is tried at that shape
  first. Generic ``/search?q={mpn}`` stays in the fetch window as fallback.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlparse

from io_utils import atomic_write_text, safe_filename
from sources.finder import is_blocked_url, official_url_score
from sources.page_ok import is_error_url

KNOWN_URLS_FILE = Path(__file__).resolve().parent / "known_urls.json"
MAX_URLS = 12
_JUNK_MARKERS = (
    "javascript:",
)
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".svg", ".webp")

_lock = threading.Lock()
_cache: dict[str, list[str]] | None = None


def _reset_cache() -> None:
    global _cache
    _cache = None


def _mpn_key(mpn: str) -> str:
    return (mpn or "").strip()


def _lookup_keys(mpn: str) -> list[str]:
    raw = _mpn_key(mpn)
    if not raw:
        return []
    keys = [raw]
    upper = raw.upper()
    if upper not in keys:
        keys.append(upper)
    if raw.endswith("Z") and len(raw) > 4:
        keys.append(raw[:-1])
        keys.append(raw[:-1].upper())
    alias = safe_filename(raw)
    if alias not in keys:
        keys.append(alias)
    seen: set[str] = set()
    ordered: list[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def url_worth_keeping(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if lowered.startswith("input:") or not lowered.startswith(("http://", "https://")):
        return False
    if is_blocked_url(raw) or is_error_url(raw):
        return False
    if any(marker in lowered for marker in _JUNK_MARKERS):
        return False
    path = urlparse(raw).path.lower()
    if path.endswith(_IMAGE_EXT):
        return False
    if not urlparse(raw).netloc:
        return False
    return True


def _keep_score(url: str) -> int:
    score = official_url_score(url)
    low = url.lower()
    if any(token in low for token in ("/p/", "/product/", "/products/", "/appliance/", "/item/", "/en-us/")):
        score = max(score, 50)
    if low.endswith(".pdf"):
        score = max(score, 45)
    if ("search?" in low or "search.html" in low or "/search/" in low) and "smartsearch" not in low:
        score = min(score, 12)
    return score


def _finalize(urls: list[str]) -> list[str]:
    kept: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not url_worth_keeping(url) or url in seen:
            continue
        seen.add(url)
        kept.append(url)
    kept.sort(key=_keep_score, reverse=True)
    strong = [url for url in kept if _keep_score(url) >= 40]
    if strong:
        kept = strong
    return kept[:MAX_URLS]


def _read_disk() -> dict[str, list[str]]:
    if not KNOWN_URLS_FILE.exists():
        return {}
    try:
        payload = json.loads(KNOWN_URLS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for key, value in payload.items():
        mpn = _mpn_key(str(key))
        if not mpn or not isinstance(value, list):
            continue
        urls = _finalize([str(item) for item in value if item])
        if urls:
            cleaned[mpn] = urls
    return cleaned


def _payload() -> dict[str, list[str]]:
    global _cache
    if _cache is None:
        _cache = _read_disk()
    return _cache


def known_urls_for(mpn: str) -> list[str]:
    payload = _payload()
    by_lower = {key.lower(): key for key in payload}
    found: list[str] = []
    for key in _lookup_keys(mpn):
        match = payload.get(key) or payload.get(by_lower.get(key.lower(), ""), [])
        found.extend(match)
    return _finalize(found)


def remembered_catalog() -> dict[str, list[str]]:
    """All per-SKU product URLs persisted from live enrich. Used by the host auditor."""
    return {key: list(urls) for key, urls in _payload().items()}


def remember_urls(mpn: str, urls: list[str]) -> None:
    key = _mpn_key(mpn)
    incoming = _finalize(urls)
    if not key or not incoming:
        return
    global _cache
    with _lock:
        payload = _read_disk()
        merged = _finalize(incoming + payload.get(key, []))
        if payload.get(key) != merged:
            payload[key] = merged
            try:
                atomic_write_text(
                    KNOWN_URLS_FILE,
                    json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                )
            except OSError:
                pass
        _cache = payload
    from sources.url_patterns import promote_templates

    promote_templates(key, incoming)


def forget_urls(mpn: str, urls: list[str]) -> None:
    key = _mpn_key(mpn)
    drop = {item.strip() for item in urls or [] if item}
    if not key or not drop:
        return
    global _cache
    with _lock:
        payload = _read_disk()
        current = payload.get(key) or []
        kept = [item for item in current if item not in drop]
        if kept == current:
            _cache = payload
            return
        if kept:
            payload[key] = kept
        else:
            payload.pop(key, None)
        try:
            atomic_write_text(
                KNOWN_URLS_FILE,
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            )
        except OSError:
            pass
        _cache = payload


def remember_bundle(mpn: str, bundle) -> None:
    urls = [getattr(bundle, "mfr_url", "") or ""]
    urls.extend(getattr(bundle, "ref_urls", None) or [])
    for item in getattr(bundle, "items", None) or []:
        urls.append(getattr(item, "source_url", "") or "")
    remember_urls(mpn, urls)


def harvest_evidence_dir(cache_dir: Path) -> dict[str, list[str]]:
    collected: dict[str, list[str]] = {}
    if not cache_dir.exists():
        return collected
    for path in sorted(cache_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        mpn = _mpn_key(str(payload.get("mpn") or path.stem))
        if not mpn:
            continue
        urls = [payload.get("mfr_url") or ""]
        urls.extend(payload.get("ref_urls") or [])
        for item in payload.get("evidence") or []:
            if isinstance(item, dict):
                urls.append(item.get("source_url") or "")
        merged = _finalize(urls + collected.get(mpn, []))
        if merged:
            collected[mpn] = merged
    return collected
