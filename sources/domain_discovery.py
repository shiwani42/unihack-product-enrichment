"""Infer manufacturer hosts when the local brand map does not know the name.

search_paths.json is only a shortcut for brands we have seen. Unseen
manufacturers are resolved from the part number + manufacturer/brand name:
guess {name}.com, then keep web-search hits on hosts that look like that name
or that are a product URL with the MPN in the path (parent-company sites).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sources.finder import is_blocked_url, is_distributor_url, url_contains_mpn, url_on_domains

LEGAL_SUFFIXES = frozenset(
    {
        "inc",
        "llc",
        "ltd",
        "corp",
        "corporation",
        "co",
        "company",
        "manufacturing",
        "mfg",
        "industries",
        "products",
        "product",
        "usa",
        "us",
        "na",
        "north",
        "america",
        "group",
        "holdings",
        "the",
        "and",
        "of",
    }
)

SKIP_GUESS_TOKENS = frozenset({"unbranded", "commodity", "generic", "none", "null"})

NOISE_LABELS = frozenset(
    {
        "wikipedia",
        "wikimedia",
        "youtube",
        "youtu",
        "facebook",
        "fb",
        "twitter",
        "instagram",
        "pinterest",
        "reddit",
        "linkedin",
        "tiktok",
        "blogspot",
        "wordpress",
        "medium",
        "duckduckgo",
        "bing",
        "google",
        "yahoo",
        "baidu",
        "yandex",
        "msn",
        "github",
        "gitlab",
        "stackoverflow",
        "quora",
        "tumblr",
        "vimeo",
        "chemblink",
        "chemicalbook",
        "lookchem",
    }
)

OFFICIAL_PATH_HINTS = (
    "/product-support",
    "/owner-center",
    "/datasheet",
    "/manual",
    "/spec",
    "/appliance",
    "/search",
)

PRODUCT_PATH_HINTS = (
    "/product",
    "/products/",
    "/p/",
    "/item/",
    "/support",
    "/spec",
    "/manual",
    "/owner",
    "/appliance",
    "/datasheet",
)


def name_tokens(name: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", (name or "").lower())
    raw = [token for token in raw if token not in LEGAL_SUFFIXES]
    tokens: list[str] = []
    initials = ""
    for token in raw:
        if len(token) == 1:
            initials += token
            continue
        if initials:
            if len(initials) >= 2:
                tokens.append(initials)
            initials = ""
        if len(token) >= 2:
            tokens.append(token)
    if initials and len(initials) >= 2:
        tokens.append(initials)
    return tokens


def guess_domains_from_name(name: str) -> list[str]:
    """Conservative {token}.com guesses from a manufacturer or brand string."""
    tokens = name_tokens(name)
    if not tokens or tokens[0].isdigit() or tokens[0] in SKIP_GUESS_TOKENS:
        return []
    domains = [f"{tokens[0]}.com"]
    for count in (2, 3, len(tokens)):
        if count < 2 or count > len(tokens):
            continue
        joined = "".join(tokens[:count])
        if 4 <= len(joined) <= 40:
            domains.append(f"{joined}.com")
    return list(dict.fromkeys(domains))


def _hostname(url: str) -> str:
    parsed = urlparse(url if "://" in (url or "") else f"https://{url or ''}")
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def host_matches_names(host: str, names: list[str]) -> bool:
    labels = {part for part in re.split(r"[.\-]", (host or "").lower()) if part}
    for name in names:
        for token in name_tokens(name):
            if len(token) < 3:
                continue
            for label in labels:
                if label == token or label.startswith(f"{token}-") or token.startswith(f"{label}-"):
                    return True
                # hunterfan.com vs Hunter, wizconnected.com vs Wiz
                if len(token) >= 4 and (token in label or label.startswith(token)):
                    return True
                if len(token) == 3 and len(label) >= 3 and label.startswith(token):
                    return True
    return False


def discover_domains_from_urls(
    urls: list[str],
    mpn: str = "",
    names: list[str] | None = None,
    limit: int = 3,
) -> list[str]:
    """Pick likely manufacturer hosts from search-result URLs."""
    names = [name for name in (names or []) if name]
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for url in urls:
        if is_blocked_url(url) or is_distributor_url(url):
            continue
        host = _hostname(url)
        if not host:
            continue
        labels = {part for part in host.split(".") if part}
        if labels & NOISE_LABELS:
            continue
        path = urlparse(url).path.lower()
        name_hit = bool(names) and host_matches_names(host, names)
        mpn_in_path = bool(mpn) and url_contains_mpn(url, mpn)
        productish = any(hint in path or hint in url.lower() for hint in PRODUCT_PATH_HINTS)
        score = 0
        if name_hit:
            score += 10
        if mpn_in_path:
            score += 8
        if productish and mpn_in_path:
            score += 6
        if mpn and mpn.lower() in url.lower() and any(hint in path or hint in url.lower() for hint in OFFICIAL_PATH_HINTS):
            score += 4
        # Name match is enough to adopt hunterfan.com from a search page.
        # Parent-company PDPs (abb.com/products/{mpn}) have no brand label in the
        # host; keep those only when the MPN is a path segment on a product URL.
        if names and not name_hit and not (mpn_in_path and productish):
            continue
        if not names and score < 8:
            continue
        if host in seen:
            continue
        seen.add(host)
        ranked.append((score, host))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [host for _score, host in ranked[:limit]]


def select_search_hits(
    urls: list[str],
    manufacturer_domains: list[str],
    mpn: str,
    names: list[str],
    limit: int,
) -> tuple[list[str], list[str]]:
    """Keep search hits on known or newly discovered manufacturer hosts."""
    discovered = discover_domains_from_urls(urls, mpn=mpn, names=names)
    combined: list[str] = []
    seen: set[str] = set()
    for domain in list(manufacturer_domains) + discovered:
        key = domain.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        combined.append(domain)
    kept: list[str] = []
    for url in urls:
        if is_blocked_url(url) or is_distributor_url(url):
            continue
        if combined and not url_on_domains(url, combined):
            continue
        if not combined:
            continue
        if url not in kept:
            kept.append(url)
        if len(kept) >= limit:
            break
    return kept, discovered
