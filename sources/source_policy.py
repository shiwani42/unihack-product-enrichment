"""Source policy from guidelines/challenge.txt.

Order:
  1. Manufacturer website and same-parent literature
  2. Reputed third-party catalogs if the manufacturer site is thin
  3. Competitors / distributors where necessary
Never: shopping / e-commerce (Amazon, eBay, Home Depot, lighting dealers, …)
and search-noise hosts (Wikipedia, FlippingBook, …). Host kinds come from
``host_taxonomy.json`` (shopping vs distributor vs third-party), not from the
gold CSV. The same rules apply to a judge SKU that is not in the sample.
Unknown manufacturer hosts are allowed when they match the brand name.

Marketing copy, item features, images, and spec PDFs stay manufacturer/family
only. Fallback pages may contribute attributes at lower confidence.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sources.finder import is_blocked_url, is_distributor_url, url_on_domains

SOURCES_FILE = Path(__file__).resolve().parent / "allowed_sources.json"

MANUFACTURER = "manufacturer"
FAMILY = "family"
THIRD_PARTY = "third_party"
DISTRIBUTOR = "distributor"
BLOCKED = "blocked"
OTHER = "other"

PRIMARY_KINDS = frozenset({MANUFACTURER, FAMILY})
ALLOWED_KINDS = frozenset({MANUFACTURER, FAMILY, THIRD_PARTY, DISTRIBUTOR})
FALLBACK_KINDS = frozenset({THIRD_PARTY, DISTRIBUTOR})


@lru_cache(maxsize=1)
def _payload() -> dict:
    empty = {"brand_families": [], "third_party": {}, "distributors": {}}
    if not SOURCES_FILE.exists():
        return empty
    try:
        data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty
    return data if isinstance(data, dict) else empty


def third_party_templates() -> dict[str, list[str]]:
    raw = _payload().get("third_party") or {}
    return raw if isinstance(raw, dict) else {}


def third_party_domains() -> list[str]:
    return list(third_party_templates())


def distributor_templates() -> dict[str, list[str]]:
    raw = _payload().get("distributors") or {}
    return raw if isinstance(raw, dict) else {}


def distributor_domains() -> list[str]:
    return list(distributor_templates())


def family_domains(manufacturer_domains: list[str]) -> list[str]:
    families = _payload().get("brand_families") or []
    extra: list[str] = []
    needles = [d.lower() for d in manufacturer_domains if d]
    for group in families:
        if not isinstance(group, list):
            continue
        lowered = [str(item).lower() for item in group]
        if any(any(needle in member or member in needle for member in lowered) for needle in needles):
            extra.extend(str(item) for item in group)
    seen: set[str] = set()
    ordered: list[str] = []
    for domain in extra:
        key = domain.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(domain)
    return ordered


def allowed_domains(
    manufacturer_domains: list[str],
    include_third_party: bool = True,
    include_distributors: bool = False,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    domains = list(manufacturer_domains) + family_domains(manufacturer_domains)
    if include_third_party:
        domains.extend(third_party_domains())
    if include_distributors:
        domains.extend(distributor_domains())
    for domain in domains:
        key = domain.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(domain)
    return ordered


def classify_url(url: str, manufacturer_domains: list[str]) -> str:
    if not url or is_blocked_url(url):
        return BLOCKED
    if url_on_domains(url, manufacturer_domains):
        return MANUFACTURER
    if url_on_domains(url, family_domains(manufacturer_domains)):
        return FAMILY
    if url_on_domains(url, third_party_domains()):
        return THIRD_PARTY
    if is_distributor_url(url) or url_on_domains(url, distributor_domains()):
        return DISTRIBUTOR
    return OTHER


def is_allowed_url(url: str, manufacturer_domains: list[str]) -> bool:
    return classify_url(url, manufacturer_domains) in ALLOWED_KINDS


def is_primary_url(url: str, manufacturer_domains: list[str]) -> bool:
    return classify_url(url, manufacturer_domains) in PRIMARY_KINDS


def is_fallback_url(url: str, manufacturer_domains: list[str]) -> bool:
    return classify_url(url, manufacturer_domains) in FALLBACK_KINDS


def apply_source_policy(bundle, url: str, manufacturer_domains: list[str]):
    """Keep attributes from allowed sources; strip manufacturer-only assets off fallback pages."""
    kind = classify_url(url, manufacturer_domains)
    if kind not in ALLOWED_KINDS:
        bundle.items = []
        bundle.marketing = ""
        bundle.features = []
        bundle.image_urls = []
        bundle.approvals = ""
        bundle.warranty = ""
        bundle.product_ids = {}
        bundle.mfr_url = ""
        return bundle
    if kind not in PRIMARY_KINDS:
        bundle.marketing = ""
        bundle.features = []
        bundle.image_urls = []
        bundle.warranty = ""
        bundle.mfr_url = ""
        for item in bundle.items:
            item.confidence = min(item.confidence, 0.68)
    return bundle
