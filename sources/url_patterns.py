"""Turn discovered product URLs into host templates that work for unseen SKUs.

Per-SKU links only help a repeat part. After live search finds
``https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF``,
the portable template
``.../product-support/{mpn}`` is what a new Frigidaire SKU from a judge
should hit. Marketing slugs unique to one catalog row stay per-SKU in
``known_urls.json``; the stable skeleton (Southwire ``/p/{mpn}``, Milwaukee
``/products/details/{mpn}``) is what the next unseen part on that host uses.
"""

from __future__ import annotations

import json
import re
import threading
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from io_utils import atomic_write_text
from sources.finder import (
    SEARCH_PATHS_FILE,
    host_uses_appliance_path,
    is_appliance_path_template,
    is_blocked_url,
    is_distributor_url,
    reset_search_path_cache,
)

# Tokens that may remain in a promoted host template. Category/SEO slugs
# (wire-cable, major-appliances, m18-brushless-...) are stripped. Do not add
# brand-specific folders here; those belong in search_paths.json.
_CATALOG_SEGMENTS = frozenset(
    {
        "en",
        "en-us",
        "en-ca",
        "en_us",
        "us",
        "ca",
        "uk",
        "p",
        "product",
        "products",
        "item",
        "items",
        "support",
        "owner-center",
        "product-support",
        "appliance",
        "appliances",
        "search",
        "manuals",
        "docs",
        "document",
        "documents",
        "spec",
        "specs",
        "specsheet",
        "specsheets",
        "gea-specs",
        "smartsearchresults",
        "html",
        "content",
        "dam",
        "global",
        "details",
        "catalog",
        "pdp",
        "sku",
        "part",
        "literature",
        "resources",
    }
)
_LOCK = threading.Lock()
_PLACEHOLDERS = ("{mpn}", "{search_mpn}")
_FILE_SUFFIXES = (".html", ".htm", ".aspx")
_SEARCH_QUERY_KEYS = frozenset(
    {"q", "query", "search", "searchtext", "searchterm", "term", "sku"}
)


def _needles(mpn: str) -> list[tuple[str, str]]:
    raw = (mpn or "").strip()
    if not raw:
        return []
    search = raw[:-1] if raw.endswith("Z") and len(raw) > 4 else raw
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(token: str, placeholder: str) -> None:
        if not token or token in seen:
            return
        seen.add(token)
        pairs.append((token, placeholder))

    add(raw, "{mpn}")
    add(quote(raw, safe="-_."), "{mpn}")
    add(quote(raw, safe=""), "{mpn}")
    add(raw.replace("/", "-"), "{mpn}")
    add(raw.replace("/", "_"), "{mpn}")
    if search != raw:
        add(search, "{search_mpn}")
        add(quote(search, safe="-_."), "{search_mpn}")
    pairs.sort(key=lambda item: -len(item[0]))
    return pairs


def templates_from_url(url: str, mpn: str) -> list[str]:
    raw = (url or "").strip()
    if not raw.startswith("http"):
        return []
    found: list[str] = []
    for needle, placeholder in _needles(mpn):
        pattern = re.compile(re.escape(needle), re.I)
        if not pattern.search(raw):
            continue
        template = pattern.sub(placeholder, raw)
        if template != raw and template not in found:
            found.append(template)
    return found


def _placeholder_stem(segment: str) -> str:
    stem = segment
    lowered = stem.lower()
    for suffix in _FILE_SUFFIXES:
        if lowered.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def _is_placeholder_segment(segment: str) -> bool:
    return _placeholder_stem(segment) in _PLACEHOLDERS


def _query_placeholders_ok(query: str) -> bool:
    if not query:
        return True
    if all(token not in query for token in _PLACEHOLDERS):
        return True
    for _key, value in parse_qsl(query, keep_blank_values=True):
        if any(token in value for token in _PLACEHOLDERS) and value not in _PLACEHOLDERS:
            return False
    return True


def is_portable_template(template: str) -> bool:
    """True when the part number is a bounded token and every other path segment is a catalog token."""
    if not template or all(token not in template for token in _PLACEHOLDERS):
        return False
    parsed = urlparse(template)
    path = parsed.path or ""
    if path.lower().endswith(".pdf"):
        return False
    if is_blocked_url(template) or is_distributor_url(template):
        return False
    if not _query_placeholders_ok(parsed.query):
        return False
    found = False
    catalog_token = False
    for segment in [part for part in path.split("/") if part]:
        if any(token in segment for token in _PLACEHOLDERS):
            if not _is_placeholder_segment(segment):
                return False
            found = True
            continue
        lowered = segment.lower()
        if lowered in _CATALOG_SEGMENTS:
            catalog_token = True
            continue
        if re.fullmatch(r"[a-z]{1,3}", lowered):
            continue
        return False
    query_keys = {key.lower() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}
    if parsed.query and any(token in parsed.query for token in _PLACEHOLDERS):
        found = True
        if query_keys & _SEARCH_QUERY_KEYS:
            catalog_token = True
    return found and catalog_token


def _skeleton_template(template: str) -> str:
    """Drop marketing/category slugs so ``/wire-cable/.../p/{mpn}`` becomes ``/p/{mpn}``."""
    parsed = urlparse(template)
    kept: list[str] = []
    for segment in [part for part in (parsed.path or "").split("/") if part]:
        if any(token in segment for token in _PLACEHOLDERS):
            if _is_placeholder_segment(segment):
                kept.append(segment)
            continue
        lowered = segment.lower()
        if lowered in _CATALOG_SEGMENTS or re.fullmatch(r"[a-z]{1,3}", lowered):
            kept.append(segment)
    path = f"/{'/'.join(kept)}" if kept else ""
    query = parsed.query
    if query and not _query_placeholders_ok(query):
        pairs = []
        for key, value in parse_qsl(query, keep_blank_values=True):
            if any(token in value for token in _PLACEHOLDERS) and value not in _PLACEHOLDERS:
                continue
            pairs.append((key, value))
        query = urlencode(pairs, safe="{}")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", query, ""))


def portable_templates(url: str, mpn: str) -> list[str]:
    found: list[str] = []
    for template in templates_from_url(url, mpn):
        for candidate in (template, _skeleton_template(template)):
            if candidate and is_portable_template(candidate) and candidate not in found:
                found.append(candidate)
    return found


def exact_portable_templates(url: str, mpn: str) -> list[str]:
    """Portable templates of the URL as requested, without stripping SEO slugs.

    Used to mark a guessed path dead. A Southwire slug 404 must not kill ``/p/{mpn}``.
    """
    return [item for item in templates_from_url(url, mpn) if is_portable_template(item)]


def _host_key(url: str) -> str:
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


def _read_paths() -> dict[str, list[str]]:
    if not SEARCH_PATHS_FILE.exists():
        return {}
    try:
        payload = json.loads(SEARCH_PATHS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    cleaned: dict[str, list[str]] = {}
    for key, value in payload.items():
        if not isinstance(value, list):
            continue
        cleaned[str(key)] = [str(item) for item in value if item]
    return cleaned


def _write_paths(payload: dict[str, list[str]]) -> None:
    atomic_write_text(
        SEARCH_PATHS_FILE,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    reset_search_path_cache()


def promote_templates(mpn: str, urls: list[str]) -> list[str]:
    """Merge portable host templates so the next unseen SKU on that brand hits them."""
    incoming: dict[str, list[str]] = {}
    for url in urls or []:
        if is_blocked_url(url) or is_distributor_url(url):
            continue
        for template in portable_templates(url, mpn):
            host = _host_key(template)
            if not host:
                continue
            if is_appliance_path_template(template) and not host_uses_appliance_path(host):
                continue
            bucket = incoming.setdefault(host, [])
            if template not in bucket:
                bucket.append(template)
    if not incoming:
        return []
    added: list[str] = []
    with _LOCK:
        payload = _read_paths()
        changed = False
        for host, templates in incoming.items():
            existing = payload.get(host, [])
            merged = list(existing)
            for template in templates:
                if template not in merged:
                    merged.append(template)
                    added.append(template)
                    changed = True
            product = [item for item in merged if "search?" not in item.lower() and "/search/" not in item.lower()]
            search = [item for item in merged if item not in product]
            payload[host] = product + search
        if changed:
            try:
                _write_paths(payload)
            except OSError:
                return []
    return added


def mine_templates(mpn_urls: dict[str, list[str]]) -> dict[str, list[str]]:
    mined: dict[str, list[str]] = {}
    for mpn, urls in (mpn_urls or {}).items():
        for url in urls or []:
            for template in portable_templates(url, mpn):
                host = _host_key(template)
                if not host:
                    continue
                bucket = mined.setdefault(host, [])
                if template not in bucket:
                    bucket.append(template)
    return mined


def promote_all(mpn_urls: dict[str, list[str]]) -> list[str]:
    added: list[str] = []
    for mpn, urls in (mpn_urls or {}).items():
        added.extend(promote_templates(mpn, urls))
    return added
