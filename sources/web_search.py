"""Discover product pages via public web search.

Engines are network-dependent: Brave may work on one judge network, DuckDuckGo
on another, Bing on a third. Try them until one returns links that mention the
MPN. Challenge/captcha/403/429 pages are misses, not evidence. The engine that
succeeded is tried first on the next SKU in this process (and in url_memory
across Vercel windows). Shopping hosts never pass. Search HTML is never
ingested as product content.
"""

from __future__ import annotations

import asyncio
import base64
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from sources.finder import is_blocked_url
from sources.source_policy import is_primary_url

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
SEARCH_TIMEOUT = httpx.Timeout(connect=3.0, read=4.0, write=4.0, pool=3.0)
SEARCH_ATTEMPT_SEC = 4.0
SEARCH_BUDGET_SEC = 12.0
SEARCH_ENGINES = ("brave", "ddg_html", "ddg_lite", "bing")
SEARCH_429_BACKOFF_SEC = 0.8
SEARCH_429_BACKOFF_CAP_SEC = 8.0
_last_engine: str | None = None
_CHALLENGE_MARKERS = (
    "captcha",
    "unusual traffic",
    "are you a robot",
    "access denied",
    "cf-browser-verification",
    "challenge-platform",
    "pardon our interruption",
    "sorry, you have been blocked",
    "enable javascript to continue",
    "checking your browser",
    "verify you are human",
)
_ENGINE_HOSTS = ("duckduckgo.", "bing.com", "google.", "brave.", "yahoo.", "microsoft.com")


def _decode_bing_u(raw: str) -> str:
    text = unquote(raw or "")
    if text.startswith("a1"):
        text = text[2:]
    pad = "=" * ((4 - len(text) % 4) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded = decoder(text + pad).decode("utf-8", "replace")
        except (ValueError, UnicodeDecodeError):
            continue
        if decoded.startswith("http"):
            return decoded
    return unquote(raw or "")


def unwrap_search_href(href: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return unquote(query["uddg"][0])
    if "u" in query and "bing.com" in (parsed.netloc or "").lower():
        return _decode_bing_u(query["u"][0])
    host = (parsed.netloc or "").lower()
    if "brave." in host and "url" in query:
        target = unquote(query["url"][0])
        if target.startswith("http"):
            return target
    return href


def cite_to_url(text: str) -> str:
    """Rebuild a URL from a Brave/Bing breadcrumb cite (host › path › mpn)."""
    raw = " ".join((text or "").split()).replace(" › ", "/").replace("›", "/")
    raw = raw.replace(" ", "")
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    host = raw.split("/")[0]
    if "." in host:
        return "https://" + raw
    return ""


def is_challenge_page(status: int, html: str) -> bool:
    """True for captcha, block, empty, or unparseable search-engine HTML."""
    if status in (0, 202, 401, 403, 429, 503):
        return True
    if status >= 400:
        return True
    text = html or ""
    if not text.strip():
        return True
    sample = text[:12000].lower()
    return any(marker in sample for marker in _CHALLENGE_MARKERS)


def parse_search_result_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "lxml")
    found: list[str] = []

    def _keep(href: str) -> None:
        if not href.startswith("http"):
            return
        host = (urlparse(href).netloc or "").lower()
        if any(token in host for token in _ENGINE_HOSTS):
            return
        if is_blocked_url(href):
            return
        if href not in found:
            found.append(href)

    for anchor in soup.find_all("a", href=True):
        _keep(unwrap_search_href(anchor["href"].strip()))
    for cite in soup.find_all("cite"):
        _keep(cite_to_url(cite.get_text(" ", strip=True)))
    return found


def filter_allowed_results(urls: list[str], manufacturer_domains: list[str], limit: int) -> list[str]:
    kept: list[str] = []
    for url in urls:
        if not is_primary_url(url, manufacturer_domains):
            continue
        if url not in kept:
            kept.append(url)
        if len(kept) >= limit:
            break
    return kept


def filter_fallback_results(
    urls: list[str],
    manufacturer_domains: list[str],
    mpn: str,
    limit: int,
    kinds: frozenset[str] | None = None,
) -> list[str]:
    """Keep fallback hosts in guideline order. Never shopping."""
    from sources.domain_discovery import discover_domains_from_urls
    from sources.finder import url_on_domains
    from sources.source_policy import classify_url, is_fallback_url

    extra = discover_domains_from_urls(urls, mpn=mpn, names=[], limit=3)
    kept: list[str] = []
    for url in urls:
        if is_blocked_url(url):
            continue
        kind = classify_url(url, manufacturer_domains)
        if kinds is not None:
            keep = kind in kinds
        else:
            keep = is_fallback_url(url, manufacturer_domains) or url_on_domains(url, extra)
        if keep and url not in kept:
            kept.append(url)
        if len(kept) >= limit:
            break
    return kept


def _mpn_needles(mpn: str) -> list[str]:
    raw = (mpn or "").strip().lower()
    if len(raw) < 4:
        return []
    needles = [raw]
    compact = raw.replace("-", "").replace("/", "").replace("_", "")
    if compact not in needles and len(compact) >= 4:
        needles.append(compact)
    return needles


def _mentions_mpn(url: str, mpn: str) -> bool:
    lowered = (url or "").lower()
    return any(needle in lowered for needle in _mpn_needles(mpn))


def last_search_engine() -> str | None:
    return _last_engine


def set_last_search_engine(name: str | None) -> None:
    global _last_engine
    _last_engine = name if name in SEARCH_ENGINES else None


def engine_order() -> tuple[str, ...]:
    """Last winner first so a judge network that only has Brave (or only DDG) stays fast."""
    if _last_engine in SEARCH_ENGINES:
        return (_last_engine,) + tuple(engine for engine in SEARCH_ENGINES if engine != _last_engine)
    return SEARCH_ENGINES


def search_queries(
    mpn: str,
    manufacturer_domains: list[str] | None = None,
    manufacturer_name: str = "",
    brand_name: str = "",
) -> list[str]:
    raw = (mpn or "").strip()
    if not raw:
        return []
    queries = [f'"{raw}"']
    label = (manufacturer_name or brand_name or "").strip()
    if label:
        queries.append(f'"{raw}" {label}')
        queries.append(f'"{raw}" {label} specifications')
    else:
        queries.append(f'"{raw}" specifications')
    from sources.source_policy import allowed_domains

    for domain in allowed_domains(manufacturer_domains or [], include_third_party=False)[:3]:
        host = domain.replace("https://", "").replace("http://", "").split("/")[0]
        if host:
            queries.append(f"{raw} site:{host}")
    seen: set[str] = set()
    ordered: list[str] = []
    for query in queries:
        if query in seen:
            continue
        seen.add(query)
        ordered.append(query)
    return ordered


def search_endpoint_urls(
    mpn: str,
    manufacturer_domains: list[str],
    manufacturer_name: str = "",
    brand_name: str = "",
) -> list[str]:
    """Public search pages used only to discover links — never ingested as evidence."""
    urls: list[str] = []
    seen: set[str] = set()
    for query in search_queries(mpn, manufacturer_domains, manufacturer_name, brand_name):
        encoded = quote_plus(query)
        for template in (
            "https://search.brave.com/search?q={query}",
            "https://html.duckduckgo.com/html/?q={query}",
            "https://lite.duckduckgo.com/lite/?q={query}",
            "https://www.bing.com/search?q={query}&setlang=en-US&cc=US",
        ):
            url = template.format(query=encoded)
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _client(ipv4: bool = False) -> httpx.AsyncClient:
    kwargs: dict = {
        "headers": BROWSER_HEADERS,
        "timeout": SEARCH_TIMEOUT,
        "follow_redirects": True,
    }
    if ipv4:
        try:
            kwargs["transport"] = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        except OSError:
            pass
    return httpx.AsyncClient(**kwargs)


async def _request(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> tuple[int, str]:
    try:
        if method == "POST":
            coro = client.post(url, **kwargs)
        else:
            coro = client.get(url, **kwargs)
        response = await asyncio.wait_for(coro, timeout=SEARCH_ATTEMPT_SEC)
    except (httpx.HTTPError, asyncio.TimeoutError, OSError):
        return 0, ""
    return response.status_code, response.text or ""


async def _engine_html(client: httpx.AsyncClient, engine: str, query: str) -> tuple[int, str]:
    encoded = quote_plus(query)
    if engine == "ddg_html":
        status, html = await _request(client, "GET", f"https://html.duckduckgo.com/html/?q={encoded}")
        urls = parse_search_result_urls(html) if not is_challenge_page(status, html) else []
        if urls:
            return status, html
        if status == 0:
            return status, html
        return await _request(
            client,
            "POST",
            "https://html.duckduckgo.com/html/",
            data={"q": query},
        )
    if engine == "ddg_lite":
        return await _request(client, "GET", f"https://lite.duckduckgo.com/lite/?q={encoded}")
    if engine == "bing":
        return await _request(
            client, "GET", f"https://www.bing.com/search?q={encoded}&setlang=en-US&cc=US"
        )
    if engine == "brave":
        return await _request(client, "GET", f"https://search.brave.com/search?q={encoded}")
    return 0, ""


async def collect_search_result_urls(
    mpn: str,
    manufacturer_domains: list[str] | None = None,
    manufacturer_name: str = "",
    brand_name: str = "",
    limit: int = 12,
) -> list[str]:
    """Try Brave, DuckDuckGo, then Bing over IPv4 first; keep MPN-matching links.

    This network rate-limits Brave on IPv6 (429) and often cannot reach DDG.
    IPv4 is tried first; dual-stack is only a fallback when IPv4 cannot connect.
    429 is a miss after backoff, not evidence.
    """
    import time

    found: list[str] = []
    queries = search_queries(mpn, manufacturer_domains, manufacturer_name, brand_name)[:2]
    engines = engine_order()
    deadline = time.monotonic() + SEARCH_BUDGET_SEC
    winner = ""
    backoff = SEARCH_429_BACKOFF_SEC
    async with _client(ipv4=True) as ipv4_client, _client() as dual_client:
        for query in queries:
            if time.monotonic() >= deadline:
                break
            got_engine = False
            for engine in engines:
                if time.monotonic() >= deadline:
                    break
                status, html = await _engine_html(ipv4_client, engine, query)
                if status == 0:
                    status, html = await _engine_html(dual_client, engine, query)
                if status == 429:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, SEARCH_429_BACKOFF_CAP_SEC)
                    status, html = await _engine_html(ipv4_client, engine, query)
                    if status == 0:
                        status, html = await _engine_html(dual_client, engine, query)
                    if status == 429:
                        continue
                if is_challenge_page(status, html):
                    continue
                urls = [url for url in parse_search_result_urls(html) if _mentions_mpn(url, mpn)]
                if not urls:
                    continue
                for url in urls:
                    if url not in found:
                        found.append(url)
                winner = engine
                got_engine = True
                backoff = SEARCH_429_BACKOFF_SEC
                break
            if got_engine and len(found) >= limit:
                break
    if winner:
        set_last_search_engine(winner)
    return found[: max(limit, 12)]
