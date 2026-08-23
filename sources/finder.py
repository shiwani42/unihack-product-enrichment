import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlparse

from app.config import DISTRIBUTOR_HOST_LABELS, ECOMMERCE_HOST_LABELS, ECOMMERCE_PATH_MARKERS

SEARCH_PATHS_FILE = Path(__file__).resolve().parent / "search_paths.json"
LEARNED_PATHS_FILE = Path(__file__).resolve().parent / "learned_paths.json"
TAXONOMY_FILE = Path(__file__).resolve().parent / "host_taxonomy.json"

# Applied to every manufacturer host, including a brand the judge invented.
# Keep this short: manufacturer fetch is capped at FETCH_URL_LIMIT (8), and
# host templates from search_paths.json are prepended for known brands.
# Brand CMS paths (owner-center, gea-specs, /products/details) stay per-host.
OFFICIAL_PATHS = (
    "/p/{mpn}",
    "/products/{mpn}",
    "/product/{mpn}",
    "/product-support/{mpn}",
    "/support/{mpn}",
)

# One generic search so an unseen host still gets a query page in the first 8.
# Query-key variants (?term=, ?searchTerm=, Magento catalogsearch) live per-host.
SEARCH_PATHS = (
    "/search?q={mpn}",
)


_OFFICIAL_HINTS = (
    ("learnwhirlpool.com/smartsearchresults", 95),
    ("/en/p/owner-center", 92),
    ("owner-center/product-support", 90),
    ("gea-specs", 88),
    ("smartsearchresults", 85),
    ("owner-center", 80),
    ("/appliance/", 65),
    ("/manuals/", 55),
    ("product-support", 45),
    ("support.", 40),
)


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


def _host_labels(host: str) -> set[str]:
    return {part for part in (host or "").split(".") if part}


def _host_in_list(host: str, hosts: frozenset[str]) -> bool:
    if not host or not hosts:
        return False
    if host in hosts:
        return True
    return any(host.endswith(f".{item}") for item in hosts)


@lru_cache(maxsize=1)
def _host_taxonomy() -> dict:
    if not TAXONOMY_FILE.exists():
        return {}
    try:
        payload = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _taxonomy_labels(key: str) -> frozenset[str]:
    return frozenset(str(item).lower() for item in (_host_taxonomy().get(key) or []) if item)


def _taxonomy_hosts(key: str) -> frozenset[str]:
    return frozenset(
        str(item).lower().removeprefix("www.")
        for item in (_host_taxonomy().get(key) or [])
        if item
    )


def shopping_host_labels() -> frozenset[str]:
    return ECOMMERCE_HOST_LABELS | _taxonomy_labels("shopping")


def distributor_host_labels() -> frozenset[str]:
    return DISTRIBUTOR_HOST_LABELS | _taxonomy_labels("distributor")


def noise_host_labels() -> frozenset[str]:
    return _taxonomy_labels("noise")


def is_blocked_url(url: str) -> bool:
    """True for shopping/e-commerce and search-noise hosts. Distributors are not blocked."""
    if not url:
        return False
    lowered = url.lower()
    if any(marker in lowered for marker in ECOMMERCE_PATH_MARKERS):
        return True
    host = _hostname(url)
    if not host:
        return False
    labels = _host_labels(host)
    if labels & shopping_host_labels():
        return True
    if labels & noise_host_labels():
        return True
    return _host_in_list(host, _taxonomy_hosts("shopping_hosts") | _taxonomy_hosts("noise_hosts"))


def is_distributor_url(url: str) -> bool:
    host = _hostname(url)
    if not host or is_blocked_url(url):
        return False
    labels = _host_labels(host)
    return bool(labels & distributor_host_labels())


def _origin(domain: str) -> str:
    raw = domain.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        host = parsed.netloc or parsed.path
        scheme = parsed.scheme or "https"
        return f"{scheme}://{host}".rstrip("/")
    host = raw.split("/")[0]
    skip_www = host.startswith(("learn", "support", "products", "docs")) or host.count(".") >= 2
    if not host.startswith("www.") and host.count(".") == 1 and not skip_www:
        host = f"www.{host}"
    return f"https://{host}".rstrip("/")


def _mpn_variants(mpn: str) -> dict[str, str]:
    encoded = quote(mpn, safe="-_.")
    search = mpn[:-1] if mpn.endswith("Z") and len(mpn) > 4 else mpn
    return {"mpn": encoded, "search_mpn": quote(search, safe="-_.")}


@lru_cache(maxsize=1)
def _domain_paths() -> dict:
    if not SEARCH_PATHS_FILE.exists():
        return {}
    try:
        payload = json.loads(SEARCH_PATHS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def _learned_paths() -> tuple[str, ...]:
    """Generic product path shapes that worked on more than one manufacturer CMS."""
    if not LEARNED_PATHS_FILE.exists():
        return ()
    try:
        payload = json.loads(LEARNED_PATHS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    raw = payload.get("paths") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return ()
    skip = set(OFFICIAL_PATHS + SEARCH_PATHS)
    cleaned: list[str] = []
    for item in raw:
        path = str(item or "").strip()
        if not path.startswith("/") or path in skip or path in cleaned:
            continue
        cleaned.append(path)
    return tuple(cleaned)


def reset_search_path_cache() -> None:
    _domain_paths.cache_clear()
    _learned_paths.cache_clear()


def url_on_domains(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    if not host:
        return False
    for domain in domains:
        needle = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
        needle = needle.removeprefix("www.")
        if needle and needle in host:
            return True
    return False


def url_on_manufacturer_domain(url: str, domains: list[str]) -> bool:
    return url_on_domains(url, domains)


def _dedupe_allowed(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        if is_blocked_url(url) or url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def is_search_url(url: str) -> bool:
    low = (url or "").lower()
    return any(token in low for token in ("search?", "search.html", "/search/", "smartsearchresults"))


def first_fetch_window(urls: list[str], limit: int) -> list[str]:
    """Product-page guesses first, with on-site search kept even if the host is crowded.

    Learned `/products/details/{mpn}` templates must not push search out of the
    first FETCH_URL_LIMIT slots. Host CMS search is tried when we have it;
    generic `/search?q=` stays as fallback for a judge SKU on an unseen CMS.
    """
    if limit <= 0:
        return []
    products: list[str] = []
    host_searches: list[str] = []
    generics: list[str] = []
    for url in urls:
        if not is_search_url(url):
            products.append(url)
        elif "search?q=" in url.lower():
            generics.append(url)
        else:
            host_searches.append(url)
    if limit == 1:
        return (products or host_searches or generics)[:1]
    fallbacks = []
    for bucket in (host_searches, generics):
        for url in bucket:
            if url not in fallbacks:
                fallbacks.append(url)
                break
    if not fallbacks:
        return products[:limit]
    kept = products[: max(limit - len(fallbacks), 0)]
    kept.extend(fallbacks)
    return kept[:limit]


def _urls_for_domains(mpn: str, domains: list[str]) -> list[str]:
    tokens = _mpn_variants(mpn)
    urls: list[str] = []
    extras = _domain_paths()
    for domain in domains:
        origin = _origin(domain)
        host = urlparse(origin).netloc.lower()
        host_has_product_extra = False
        for key, templates in extras.items():
            if key not in host:
                continue
            for template in templates:
                urls.append(template.format(**tokens))
                if not is_search_url(template):
                    host_has_product_extra = True
        paths = SEARCH_PATHS if host_has_product_extra else OFFICIAL_PATHS + _learned_paths() + SEARCH_PATHS
        for path in paths:
            urls.append(origin + path.format(**tokens))
    from sources.dead_paths import drop_dead_urls

    return drop_dead_urls(_dedupe_allowed(urls), mpn)


def _urls_from_templates(mpn: str, templates_by_domain: dict[str, list[str]]) -> list[str]:
    tokens = _mpn_variants(mpn)
    urls: list[str] = []
    for templates in templates_by_domain.values():
        for template in templates:
            urls.append(template.format(**tokens))
    return _dedupe_allowed(urls)


def candidate_mfr_urls(mpn: str, domains: list[str]) -> list[str]:
    """Manufacturer-domain URLs. Shopping hosts are dropped.

    Known product pages for this SKU (from prior live search) come first so
    later runs hit the real page instead of a brand search template.
    """
    from sources.known_urls import known_urls_for

    remembered = []
    for url in known_urls_for(mpn):
        if is_blocked_url(url) or is_distributor_url(url):
            continue
        if not domains or url_on_domains(url, domains):
            remembered.append(url)
    return _dedupe_allowed(remembered + _urls_for_domains(mpn, domains))


def candidate_family_urls(mpn: str, manufacturer_domains: list[str]) -> list[str]:
    from sources.source_policy import family_domains

    extra = [d for d in family_domains(manufacturer_domains) if not url_on_domains(f"https://{d}/", manufacturer_domains)]
    return _urls_for_domains(mpn, extra)


def candidate_third_party_urls(mpn: str) -> list[str]:
    from sources.source_policy import third_party_templates

    return _urls_from_templates(mpn, third_party_templates())


def candidate_distributor_urls(mpn: str) -> list[str]:
    from sources.source_policy import distributor_templates

    return _urls_from_templates(mpn, distributor_templates())


def url_contains_mpn(url: str, mpn: str) -> bool:
    """True when the part number is a path segment or query value, not a substring."""
    needle = (mpn or "").strip().lower()
    if len(needle) < 3:
        return False
    parsed = urlparse(url or "")
    from urllib.parse import parse_qsl, unquote

    values = {unquote(value).lower() for _key, value in parse_qsl(parsed.query, keep_blank_values=True)}
    if needle in values:
        return True
    segments = [unquote(part).lower().rsplit(".", 1)[0] for part in (parsed.path or "").split("/") if part]
    return needle in segments


def official_url_score(url: str, mpn: str = "") -> int:
    """Prefer manufacturer product-support / literature pages over generic search."""
    if not url or is_blocked_url(url):
        return -1
    low = url.lower()
    if low.endswith(".pdf"):
        return 0
    if any(token in low for token in ("/login", "/logout", "/signin", "/cart", "/account", "/api/auth")):
        return -1
    score = 10
    for hint, points in _OFFICIAL_HINTS:
        if hint in low:
            score = max(score, points)
    if mpn and url_contains_mpn(url, mpn):
        needle = mpn.strip().lower()
        path = (urlparse(url).path or "").lower()
        if needle in [part.rsplit(".", 1)[0] for part in path.split("/") if part]:
            score = max(score, 80)
        else:
            score = max(score, 40)
    if "manuals-and-downloads" in low and not url_contains_mpn(url, mpn):
        score = min(score, 18)
    if "search?" in low or "search.html" in low:
        score = min(score, 15)
    return score


def best_mfr_url(mpn: str, domains: list[str]) -> str:
    from sources.known_urls import _keep_score, known_urls_for

    def _not_query_search(url: str) -> bool:
        low = (url or "").lower()
        return "search?" not in low and not low.endswith("search.html")

    known = [
        url
        for url in known_urls_for(mpn)
        if not is_blocked_url(url)
        and not is_distributor_url(url)
        and not url.lower().endswith(".pdf")
        and (not domains or url_on_domains(url, domains))
        and _not_query_search(url)
    ]
    if known:
        return max(known, key=_keep_score)
    candidates = [
        url
        for url in candidate_mfr_urls(mpn, domains)
        if not url.lower().endswith(".pdf") and _not_query_search(url)
    ]
    if not candidates:
        return ""
    return max(candidates, key=lambda url: official_url_score(url, mpn))
