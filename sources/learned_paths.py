"""Cross-host product path shapes learned from live manufacturer pages.

``search_paths.json`` is per-host: Frigidaire owner-center, Milwaukee
``/products/details/{mpn}``. A judge SKU on a brand we have never mapped
still needs a short generic guess list. Paths that showed up on two or more
manufacturer hosts, plus a few CMS shapes that already work on one mapped
brand, are stored here and appended to ``OFFICIAL_PATHS`` for unseen hosts.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from io_utils import atomic_write_text
from sources.finder import (
    LEARNED_PATHS_FILE,
    OFFICIAL_PATHS,
    SEARCH_PATHS,
    is_search_url,
    reset_search_path_cache,
)
from sources.url_patterns import _host_key, mine_templates, portable_templates

# Brand-family CMS. Useful on that host; 404 noise on an unseen tool brand.
_SKIP_SHAPES = (
    "owner-center",
    "gea-specs",
    "smartsearch",
    "learnwhirlpool",
)

# Adobe Commerce / Magento storefronts and appliance PDPs we have already
# seen. Included when they appear on at least one mapped host, even if the
# sample only has one brand on that CMS.
_SEED_SHAPES = (
    "/appliance/{mpn}",
    "/en-us/product/{mpn}",
    "/products/details/{mpn}",
)

LEARNED_PATHS_CAP = 2
MAX_SHAPE_SEGMENTS = 3


def template_path_shape(template: str) -> str | None:
    """Host-independent ``/products/{mpn}`` shape, or None if it should stay per-host."""
    raw = (template or "").strip()
    if not raw or is_search_url(raw):
        return None
    parsed = urlparse(raw if "://" in raw else f"https://placeholder.example{raw}")
    path = parsed.path or ""
    if "{mpn}" not in path and "{search_mpn}" not in path:
        return None
    lowered = path.lower()
    if any(token in lowered for token in _SKIP_SHAPES):
        return None
    segments = [part for part in path.split("/") if part]
    if not segments or len(segments) > MAX_SHAPE_SEGMENTS:
        return None
    return path


def mine_cross_host_paths(
    templates_by_host: dict[str, list[str]],
    min_hosts: int = 2,
    cap: int = LEARNED_PATHS_CAP,
    skip_paths: tuple[str, ...] | None = None,
) -> list[str]:
    """Path shapes used by ``min_hosts`` or more manufacturer hosts."""
    skip = set(skip_paths if skip_paths is not None else OFFICIAL_PATHS + SEARCH_PATHS)
    hosts_for_shape: dict[str, set[str]] = {}
    for host, templates in (templates_by_host or {}).items():
        key = (host or "").lower().removeprefix("www.")
        if not key:
            continue
        for template in templates or []:
            shape = template_path_shape(template)
            if not shape or shape in skip:
                continue
            hosts_for_shape.setdefault(shape, set()).add(key)
    ranked = sorted(
        ((shape, len(hosts)) for shape, hosts in hosts_for_shape.items() if len(hosts) >= min_hosts),
        key=lambda item: (-item[1], item[0]),
    )
    return [shape for shape, _count in ranked[:cap]]


def collect_host_templates(
    search_paths: dict[str, list[str]] | None = None,
    mpn_urls: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Union of per-host templates from search_paths and portable SKU URLs."""
    collected: dict[str, list[str]] = {}

    def add(host: str, template: str) -> None:
        if not host or not template:
            return
        bucket = collected.setdefault(host, [])
        if template not in bucket:
            bucket.append(template)

    for host, templates in (search_paths or {}).items():
        key = (host or "").lower().removeprefix("www.")
        for template in templates or []:
            add(key, str(template))
            add(_host_key(str(template)), str(template))
    for mpn, urls in (mpn_urls or {}).items():
        for url in urls or []:
            for template in portable_templates(url, mpn):
                add(_host_key(template), template)
        for host, templates in mine_templates({mpn: list(urls or [])}).items():
            for template in templates:
                add(host, template)
    return collected


def _seed_shapes_present(templates_by_host: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    for templates in (templates_by_host or {}).values():
        for template in templates or []:
            shape = template_path_shape(template)
            if shape:
                seen.add(shape)
    return [shape for shape in _SEED_SHAPES if shape in seen]


def merge_learned_paths(templates_by_host: dict[str, list[str]], cap: int = LEARNED_PATHS_CAP) -> list[str]:
    skip = set(OFFICIAL_PATHS + SEARCH_PATHS)
    mined = mine_cross_host_paths(templates_by_host, min_hosts=2, cap=cap, skip_paths=tuple(skip))
    merged: list[str] = []
    for shape in mined + _seed_shapes_present(templates_by_host):
        if shape in skip or shape in merged:
            continue
        merged.append(shape)
        if len(merged) >= cap:
            break
    return merged


def load_learned_paths(path: Path | None = None) -> list[str]:
    target = path or LEARNED_PATHS_FILE
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return []
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("paths") or []
    else:
        return []
    skip = set(OFFICIAL_PATHS + SEARCH_PATHS)
    cleaned: list[str] = []
    for item in raw:
        shape = str(item or "").strip()
        if not shape or shape in skip or shape in cleaned:
            continue
        if template_path_shape(f"https://example.com{shape}") != shape:
            continue
        cleaned.append(shape)
    return cleaned


def write_learned_paths(paths: list[str], path: Path | None = None) -> None:
    target = path or LEARNED_PATHS_FILE
    atomic_write_text(
        target,
        json.dumps({"paths": list(paths)}, indent=2, ensure_ascii=False) + "\n",
    )
    reset_search_path_cache()


def _read_json_map(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def refresh_learned_paths(
    extra_mpn_urls: dict[str, list[str]] | None = None,
    search_paths_file: Path | None = None,
    known_urls_file: Path | None = None,
    dest: Path | None = None,
) -> list[str]:
    """Rebuild generic path guesses from host templates and remembered product URLs."""
    from sources.finder import SEARCH_PATHS_FILE
    from sources.known_urls import KNOWN_URLS_FILE

    search_payload = _read_json_map(search_paths_file or SEARCH_PATHS_FILE)
    known_payload = _read_json_map(known_urls_file or KNOWN_URLS_FILE)
    mpn_urls: dict[str, list[str]] = {}
    for source in (known_payload, extra_mpn_urls or {}):
        for mpn, urls in source.items():
            if not isinstance(urls, list):
                continue
            bucket = mpn_urls.setdefault(str(mpn), [])
            for url in urls:
                if url and url not in bucket:
                    bucket.append(str(url))
    templates = collect_host_templates(search_payload, mpn_urls)
    paths = merge_learned_paths(templates)
    write_learned_paths(paths, dest)
    return paths
