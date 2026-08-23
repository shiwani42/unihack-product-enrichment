"""Look up a company's official website on Wikidata (free, no API key).

Wikipedia article text is never product evidence. This only reads P856
(official website) so an unmapped brand can start from a real host instead
of {name}.com. Mapped brands do not call it.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx

from app.config import USER_AGENT
from sources.domain_discovery import host_matches_names
from sources.finder import is_blocked_url, is_distributor_url

WD_API = "https://www.wikidata.org/w/api.php"
_TIMEOUT = httpx.Timeout(connect=2.0, read=4.0, write=4.0, pool=2.0)
_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# Company / brand / manufacturer. Humans, films, and songs are rejected.
_ALLOW_P31 = frozenset(
    {
        "Q4830453",  # business
        "Q783794",  # company
        "Q167270",  # brand
        "Q431289",  # brand
        "Q6881511",  # enterprise
        "Q891723",  # public company
        "Q161726",  # multinational
        "Q13235160",  # manufacturer
        "Q1639109",  # manufacturing
        "Q507619",  # retailer skipped? no keep manufacturer
    }
)
_REJECT_P31 = frozenset(
    {
        "Q5",  # human
        "Q11424",  # film
        "Q7366",  # song
        "Q134556",  # single
        "Q5398426",  # television series
        "Q16521",  # taxon
    }
)
_COMPANY_WORDS = (
    "manufacturer",
    "company",
    "brand",
    "corporation",
    "tools",
    "lighting",
    "appliance",
    "electronics",
    "building",
    "industrial",
    "hardware",
)
_SKIP_WORDS = (
    "disambiguation",
    "family name",
    "given name",
    "human",
    "film",
    "song",
    "video game",
    "fictional",
    "wikipedia",
)

_cache: dict[str, list[str]] = {}


def wikidata_enabled() -> bool:
    return os.environ.get("UNILOG_WIKIDATA", "1").strip().lower() not in {"0", "false", "no"}


def _get_json(params: dict) -> dict:
    with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        response = client.get(WD_API, params=params)
        response.raise_for_status()
        payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _claim_values(entity: dict, prop: str) -> list:
    claims = ((entity.get("claims") or {}).get(prop) or [])
    values = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if value is not None:
            values.append(value)
    return values


def _p31_ids(entity: dict) -> set[str]:
    ids: set[str] = set()
    for value in _claim_values(entity, "P31"):
        if isinstance(value, dict) and value.get("id"):
            ids.add(str(value["id"]))
    return ids


def _official_urls(entity: dict) -> list[str]:
    urls: list[str] = []
    for value in _claim_values(entity, "P856"):
        if isinstance(value, str) and value.startswith("http"):
            urls.append(value)
    return urls


def _host(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _description(entity: dict, hit: dict) -> str:
    descriptions = entity.get("descriptions") or {}
    english = descriptions.get("en") if isinstance(descriptions, dict) else None
    if isinstance(english, dict):
        return str(english.get("value") or "")
    return str(hit.get("description") or "")


def _usable_entity(entity: dict, hit: dict, names: list[str]) -> bool:
    desc = _description(entity, hit).lower()
    if any(token in desc for token in _SKIP_WORDS):
        return False
    p31 = _p31_ids(entity)
    if p31 & _REJECT_P31:
        return False
    if p31 & _ALLOW_P31:
        return True
    if any(word in desc for word in _COMPANY_WORDS):
        return True
    label = str((hit.get("label") or "")).lower()
    return bool(names) and any(name.lower() == label for name in names if name)


def official_website_hosts(names: list[str]) -> list[str]:
    """Official website hosts from Wikidata P856. Empty when disabled or unsure."""
    if not wikidata_enabled():
        return []
    query = max((str(name).strip() for name in names if name and len(str(name).strip()) >= 3), key=len, default="")
    if not query:
        return []
    cached = _cache.get(query.lower())
    if cached is not None:
        return list(cached)
    hosts: list[str] = []
    try:
        search = _get_json(
            {
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "type": "item",
                "limit": "5",
                "format": "json",
            }
        )
        hits = [hit for hit in (search.get("search") or []) if isinstance(hit, dict) and hit.get("id")]
        ids = [str(hit["id"]) for hit in hits[:5]]
        if not ids:
            _cache[query.lower()] = []
            return []
        entities = (
            _get_json(
                {
                    "action": "wbgetentities",
                    "ids": "|".join(ids),
                    "props": "claims|descriptions|labels",
                    "languages": "en",
                    "format": "json",
                }
            ).get("entities")
            or {}
        )
        hit_by_id = {str(hit["id"]): hit for hit in hits}
        for entity_id in ids:
            entity = entities.get(entity_id)
            if not isinstance(entity, dict):
                continue
            hit = hit_by_id.get(entity_id) or {}
            if not _usable_entity(entity, hit, names):
                continue
            for url in _official_urls(entity):
                if is_blocked_url(url) or is_distributor_url(url):
                    continue
                host = _host(url)
                if not host or host.endswith("wikipedia.org") or host.endswith("wikidata.org"):
                    continue
                if names and not host_matches_names(host, names):
                    continue
                if host not in hosts:
                    hosts.append(host)
            if hosts:
                break
    except (httpx.HTTPError, OSError, ValueError, TypeError):
        hosts = []
    _cache[query.lower()] = hosts
    return list(hosts)
