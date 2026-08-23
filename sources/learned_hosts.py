"""Host-level lessons from a live SKU, reused on the next unseen part.

Winning manufacturer URLs already become host templates (search_paths) and
404s become dead_paths. This file is the quality half of that loop: a page
that looks like a local storefront (Magento town_name, Angular junk, pixel
Size, hex Color) on a host that is not the brand is remembered so later SKUs
do not treat that host as the manufacturer. No SKU list; the next judge part
on a new dealer CMS teaches the rest of the batch and the Vercel url_memory
snapshot.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

from extract.evidence import EvidenceBundle
from io_utils import atomic_write_text
from normalize.values import cleanse_attribute

LEARNED_HOSTS_FILE = Path(__file__).resolve().parents[1] / "data" / "learned_hosts.json"
MAX_STOREFRONT_HOSTS = 500
JUNK_THRESHOLD = 2

_JUNK_FIELDS = frozenset(
    {
        "town_name",
        "sep",
        "city",
        "state",
        "zip",
        "postal",
        "address",
        "phone",
        "site_name",
        "state_name",
        "country_name",
        "categories",
        "category",
        "latitude",
        "longitude",
        "hours",
    }
)
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_TEMPLATE_JUNK = re.compile(r"\{\{|}}|attributeValue", re.I)
_TOWN_LABEL = re.compile(r"town_name", re.I)
_ANGULAR = re.compile(r"\{\{\s*attributeValue\s*\}\}", re.I)
_LOCAL_BUSINESS = re.compile(r'"@type"\s*:\s*"LocalBusiness"', re.I)
_LOCALITY = re.compile(r"addressLocality", re.I)

_lock = threading.Lock()
_cache: dict[str, list[str]] | None = None


def _reset_cache() -> None:
    global _cache
    _cache = None


def _hostname(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.removeprefix("www.")


def _read() -> dict[str, list[str]]:
    global _cache
    if _cache is not None:
        return _cache
    if not LEARNED_HOSTS_FILE.exists():
        _cache = {"storefront": []}
        return _cache
    try:
        payload = json.loads(LEARNED_HOSTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        _cache = {"storefront": []}
        return _cache
    hosts: list[str] = []
    raw = payload.get("storefront") if isinstance(payload, dict) else payload
    if isinstance(raw, dict):
        raw = list(raw)
    for item in raw if isinstance(raw, list) else []:
        host = _hostname(str(item))
        if host and host not in hosts:
            hosts.append(host)
    _cache = {"storefront": hosts[:MAX_STOREFRONT_HOSTS]}
    return _cache


def _write(payload: dict[str, list[str]]) -> None:
    LEARNED_HOSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        LEARNED_HOSTS_FILE,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def storefront_hosts() -> list[str]:
    return list(_read().get("storefront") or [])


def is_learned_storefront(url: str) -> bool:
    host = _hostname(url)
    if not host:
        return False
    known = storefront_hosts()
    if host in known:
        return True
    return any(host.endswith(f".{item}") for item in known)


def note_storefront_host(url: str) -> None:
    host = _hostname(url)
    if not host:
        return
    global _cache
    with _lock:
        payload = _read()
        hosts = payload.setdefault("storefront", [])
        if host in hosts:
            _cache = payload
            return
        if len(hosts) >= MAX_STOREFRONT_HOSTS:
            _cache = payload
            return
        hosts.append(host)
        try:
            _write(payload)
        except OSError:
            return
        _cache = payload


def _junk_value(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if _TEMPLATE_JUNK.search(text) or _HEX_COLOR.fullmatch(text):
        return True
    if re.search(r"with more than", text, re.I):
        return True
    return False


def _item_kind(field: str, value: str, uom: str = "") -> str:
    label = (field or "").strip()
    text = (value or "").strip()
    if not text:
        return "neutral"
    if label.lower() in _JUNK_FIELDS or _junk_value(text):
        return "junk"
    cleaned, _unit = cleanse_attribute(label, text, uom or "", "generic_industrial")
    if cleaned:
        return "useful"
    if label.lower() in {"size", "width", "height", "color", "finish", "with"}:
        return "junk"
    return "neutral"


def html_storefront_chrome(html: str) -> int:
    text = html or ""
    score = 0
    if _TOWN_LABEL.search(text):
        score += 2
    if _ANGULAR.search(text):
        score += 2
    if _LOCAL_BUSINESS.search(text) and _LOCALITY.search(text):
        score += 1
    return score


def _host_is_protected(url: str, names: list[str]) -> bool:
    from sources.domain_discovery import host_matches_names
    from sources.finder import is_distributor_url, is_search_url

    if not url or is_search_url(url) or is_distributor_url(url):
        return True
    host = _hostname(url)
    if not host:
        return True
    return bool(names) and host_matches_names(host, names)


def looks_like_storefront_page(
    url: str,
    html: str,
    bundle: EvidenceBundle | None,
    names: list[str] | None = None,
) -> bool:
    if _host_is_protected(url, [name for name in (names or []) if name]):
        return False
    junk = 0
    useful = 0
    for item in getattr(bundle, "items", None) or []:
        source = getattr(item, "source_url", "") or url
        if _hostname(source) != _hostname(url):
            continue
        kind = _item_kind(getattr(item, "field", ""), getattr(item, "value", ""), getattr(item, "uom", "") or "")
        if kind == "useful":
            useful += 1
        elif kind == "junk":
            junk += 1
    if useful:
        return False
    chrome = html_storefront_chrome(html)
    return chrome >= 1 or junk >= JUNK_THRESHOLD


def learn_from_page(
    url: str,
    html: str,
    bundle: EvidenceBundle | None,
    names: list[str] | None = None,
) -> bool:
    if not looks_like_storefront_page(url, html, bundle, names):
        return False
    note_storefront_host(url)
    return True


def learn_from_bundle(bundle: EvidenceBundle | None, names: list[str] | None = None) -> list[str]:
    if bundle is None:
        return []
    hosts: dict[str, str] = {}
    if bundle.mfr_url:
        hosts[_hostname(bundle.mfr_url)] = bundle.mfr_url
    for item in bundle.items or []:
        source = getattr(item, "source_url", "") or ""
        host = _hostname(source)
        if host:
            hosts.setdefault(host, source)
    marked: list[str] = []
    for url in hosts.values():
        if learn_from_page(url, "", bundle, names):
            marked.append(_hostname(url))
    return marked


def scrub_bundle(bundle: EvidenceBundle | None) -> None:
    if bundle is None:
        return
    from sources.finder import is_blocked_url, looks_like_dealer_storefront

    def drop(url: str) -> bool:
        raw = (url or "").strip()
        if not raw:
            return False
        return is_learned_storefront(raw) or is_blocked_url(raw) or looks_like_dealer_storefront(raw)

    if drop(bundle.mfr_url or ""):
        bundle.mfr_url = ""
        bundle.marketing = ""
        bundle.features = []
        bundle.image_urls = []
        bundle.product_ids = {}
    bundle.ref_urls = [url for url in (bundle.ref_urls or []) if not drop(url)]
    bundle.items = [item for item in (bundle.items or []) if not drop(getattr(item, "source_url", "") or "")]
    bundle.image_urls = [url for url in (bundle.image_urls or []) if not drop(url)]


def apply_run_lessons(bundle: EvidenceBundle | None, names: list[str] | None = None) -> None:
    learn_from_bundle(bundle, names)
    scrub_bundle(bundle)
