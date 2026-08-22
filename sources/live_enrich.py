"""Live fetch in guideline order: manufacturer, family, then fallback sources."""

import asyncio
import concurrent.futures

from app.config import (
    FETCH_TIMEOUT,
    FETCH_URL_LIMIT,
    FOLLOW_URL_LIMIT,
    SEARCH_URL_LIMIT,
    SECONDARY_URL_LIMIT,
    THIRD_PARTY_URL_LIMIT,
    DISTRIBUTOR_URL_LIMIT,
    PDF_URL_LIMIT,
    FETCH_PDFS,
)
from extract.cache import save_cached_bundle
from extract.evidence import EvidenceBundle
from extract.html_specs import extract_from_html
from extract.merge import merge_bundles
from extract.pdf_specs import fetch_pdf_evidence
from extract.ref_discovery import discover_pdf_links, discover_product_links
from extract.structured import extract_structured_data
from sources.async_fetcher import fetch_all_pages
from sources.dead_paths import drop_dead_urls, note_outcome
from sources.page_ok import is_error_url, is_not_found, is_usable_page
from sources.finder import (
    best_mfr_url,
    candidate_distributor_urls,
    candidate_family_urls,
    candidate_mfr_urls,
    candidate_third_party_urls,
    first_fetch_window,
    is_blocked_url,
    official_url_score,
)
from sources.raw_cache import save_raw_html
from sources.source_policy import (
    DISTRIBUTOR,
    THIRD_PARTY,
    apply_source_policy,
    classify_url,
    is_allowed_url,
    is_primary_url,
)
from sources.web_search import collect_search_result_urls, filter_fallback_results
from sources.domain_discovery import guess_domains_from_name, select_search_hits
from sources.known_urls import known_urls_for, remember_bundle, remember_urls


def _run_coroutine_blocking(coroutine):
    """Run a coroutine to completion from sync code, even inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    def _execute():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coroutine)
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_execute).result()


def _replace(dst: EvidenceBundle, src: EvidenceBundle) -> None:
    dst.mfr_url = src.mfr_url
    dst.ref_urls = src.ref_urls
    dst.items = src.items
    dst.marketing = src.marketing
    dst.features = src.features
    dst.approvals = src.approvals
    dst.warranty = src.warranty
    dst.product_ids = src.product_ids
    dst.image_urls = src.image_urls


def _web_search_enabled() -> bool:
    import os

    return os.environ.get("UNILOG_WEB_SEARCH", "1").strip().lower() not in {"0", "false", "no"}


def _needs_fallback(bundle: EvidenceBundle) -> bool:
    """True when manufacturer/family evidence is too thin for attributes."""
    return len(bundle.items) < 2


def _follow_hosts(url: str, manufacturer_domains: list[str]) -> list[str]:
    from sources.source_policy import allowed_domains

    host = url.split("/")[2] if "://" in url else ""
    if host:
        return [host] + manufacturer_domains
    return allowed_domains(manufacturer_domains)


def _ingest_page(
    bundle: EvidenceBundle,
    html: str,
    url: str,
    mpn: str,
    manufacturer_domains: list[str],
) -> tuple[list[str], list[str]]:
    if not is_allowed_url(url, manufacturer_domains) or is_error_url(url):
        return [], []
    save_raw_html(mpn, html, url)
    page_bundle = merge_bundles(extract_from_html(html, url), extract_structured_data(html, url))
    apply_source_policy(page_bundle, url, manufacturer_domains)
    contributed = (
        page_bundle.items
        or page_bundle.marketing
        or page_bundle.features
        or page_bundle.image_urls
        or page_bundle.approvals
        or page_bundle.product_ids
    )
    if contributed:
        merged = merge_bundles(bundle, page_bundle)
        _replace(bundle, merged)
        if is_primary_url(url, manufacturer_domains):
            if official_url_score(url) >= official_url_score(bundle.mfr_url):
                bundle.mfr_url = url
        elif url not in bundle.ref_urls:
            bundle.ref_urls.append(url)
    pdfs = [
        link
        for link in discover_pdf_links(html, url)
        if is_primary_url(link, manufacturer_domains)
    ]
    products = discover_product_links(
        html,
        url,
        mpn,
        _follow_hosts(url, manufacturer_domains),
        limit=FOLLOW_URL_LIMIT,
    )
    return products, pdfs


def _fetch_tier(
    bundle: EvidenceBundle,
    start_urls: list[str],
    mpn: str,
    manufacturer_domains: list[str],
    seen: set[str],
    follow: bool = True,
) -> list[str]:
    start_urls = drop_dead_urls(
        [u for u in start_urls if u not in seen and not is_blocked_url(u) and not is_error_url(u)],
        mpn,
    )
    for url in start_urls:
        seen.add(url)
    if not start_urls:
        return []

    pdf_links: list[str] = []
    follow_urls: list[str] = []
    pages = _run_coroutine_blocking(fetch_all_pages(start_urls, timeout=FETCH_TIMEOUT))
    for status, html, final_url, requested in pages:
        note_outcome(requested, mpn, status, html, final_url)
        if is_not_found(status, html, final_url) or is_not_found(status, html, requested):
            from sources.known_urls import forget_urls

            forget_urls(mpn, [requested, final_url])
        if not is_usable_page(status, html, final_url):
            continue
        products, pdfs = _ingest_page(bundle, html, final_url, mpn, manufacturer_domains)
        pdf_links.extend(pdfs)
        for product in products:
            if product not in seen and is_allowed_url(product, manufacturer_domains) and not is_error_url(product):
                seen.add(product)
                follow_urls.append(product)

    if follow and follow_urls:
        more = _run_coroutine_blocking(
            fetch_all_pages(follow_urls[:FOLLOW_URL_LIMIT], timeout=FETCH_TIMEOUT)
        )
        for status, html, final_url, requested in more:
            note_outcome(requested, mpn, status, html, final_url)
            if not is_usable_page(status, html, final_url):
                continue
            _, pdfs = _ingest_page(bundle, html, final_url, mpn, manufacturer_domains)
            pdf_links.extend(pdfs)
    return pdf_links


def _hosts_from_urls(urls: list[str]) -> list[str]:
    hosts: list[str] = []
    for url in urls:
        host = url.split("/")[2] if "://" in url else ""
        host = host.lower().removeprefix("www.")
        if host:
            hosts.append(host)
    return hosts


def _split_known_urls(mpn: str, manufacturer_domains: list[str]) -> tuple[list[str], list[str]]:
    from sources.source_policy import BLOCKED, FALLBACK_KINDS, classify_url

    primary: list[str] = []
    fallback: list[str] = []
    for url in known_urls_for(mpn):
        kind = classify_url(url, manufacturer_domains)
        if kind == BLOCKED:
            continue
        if kind in FALLBACK_KINDS:
            fallback.append(url)
        else:
            primary.append(url)
    return primary, fallback


def _discover_search_urls(
    mpn: str,
    manufacturer_domains: list[str],
    seen: set[str],
    manufacturer_name: str = "",
    brand_name: str = "",
) -> tuple[list[str], list[str], list[str]]:
    if not _web_search_enabled():
        return [], [], []
    from sources.source_policy import family_domains

    names = [name for name in (manufacturer_name, brand_name) if name]
    found = _run_coroutine_blocking(
        collect_search_result_urls(
            mpn,
            manufacturer_domains,
            manufacturer_name=manufacturer_name,
            brand_name=brand_name,
            limit=max(SEARCH_URL_LIMIT * 2, 8),
        )
    )
    seed = list(manufacturer_domains) + family_domains(manufacturer_domains)
    hits, extra_domains = select_search_hits(found, seed, mpn, names, SEARCH_URL_LIMIT)
    return [url for url in hits if url not in seen], extra_domains, found


def fetch_manufacturer_evidence(
    mpn: str,
    domains: list[str],
    max_urls: int | None = None,
    fetch_pdfs: bool = True,
    manufacturer_name: str = "",
    brand_name: str = "",
) -> EvidenceBundle:
    bundle = EvidenceBundle()
    names = [name for name in (manufacturer_name, brand_name) if name]
    manufacturer_domains = list(domains or [])
    if not manufacturer_domains:
        guessed: list[str] = []
        for name in names:
            guessed.extend(guess_domains_from_name(name))
        manufacturer_domains = list(dict.fromkeys(guessed))
    url_limit = max_urls or FETCH_URL_LIMIT
    seen: set[str] = set()
    pdf_links: list[str] = []
    known_primary, known_fallback = _split_known_urls(mpn, manufacturer_domains)
    if known_primary:
        manufacturer_domains = list(dict.fromkeys(manufacturer_domains + _hosts_from_urls(known_primary)))
        pdf_links.extend(
            _fetch_tier(bundle, known_primary[:url_limit], mpn, manufacturer_domains, seen)
        )

    if manufacturer_domains:
        pdf_links.extend(
            _fetch_tier(
                bundle,
                first_fetch_window(candidate_mfr_urls(mpn, manufacturer_domains), url_limit),
                mpn,
                manufacturer_domains,
                seen,
            )
        )
        pdf_links.extend(
            _fetch_tier(
                bundle,
                candidate_family_urls(mpn, manufacturer_domains)[:SECONDARY_URL_LIMIT],
                mpn,
                manufacturer_domains,
                seen,
            )
        )
    need_search = (not manufacturer_domains) or _needs_fallback(bundle) or not bundle.mfr_url
    if need_search:
        search_hits, extra_domains, found = _discover_search_urls(
            mpn,
            manufacturer_domains,
            seen,
            manufacturer_name=manufacturer_name,
            brand_name=brand_name,
        )
        if extra_domains:
            manufacturer_domains = list(dict.fromkeys(manufacturer_domains + extra_domains))
        if search_hits:
            remember_urls(mpn, search_hits)
            pdf_links.extend(_fetch_tier(bundle, search_hits, mpn, manufacturer_domains, seen))
    else:
        found = []

    # Transcript order: third-party, then distributors, only where necessary.
    if _needs_fallback(bundle):
        known_third = [
            url
            for url in known_fallback
            if url not in seen and classify_url(url, manufacturer_domains) == THIRD_PARTY
        ]
        third_hits = [
            url
            for url in filter_fallback_results(
                found, manufacturer_domains, mpn, SEARCH_URL_LIMIT, kinds=frozenset({THIRD_PARTY})
            )
            if url not in seen
        ]
        pdf_links.extend(
            _fetch_tier(
                bundle,
                list(dict.fromkeys(known_third + candidate_third_party_urls(mpn)[:THIRD_PARTY_URL_LIMIT] + third_hits)),
                mpn,
                manufacturer_domains,
                seen,
            )
        )
    if _needs_fallback(bundle):
        known_dist = [
            url
            for url in known_fallback
            if url not in seen and classify_url(url, manufacturer_domains) == DISTRIBUTOR
        ]
        dist_hits = [
            url
            for url in filter_fallback_results(
                found, manufacturer_domains, mpn, SEARCH_URL_LIMIT, kinds=frozenset({DISTRIBUTOR})
            )
            if url not in seen
        ]
        pdf_links.extend(
            _fetch_tier(
                bundle,
                list(dict.fromkeys(known_dist + candidate_distributor_urls(mpn)[:DISTRIBUTOR_URL_LIMIT] + dist_hits)),
                mpn,
                manufacturer_domains,
                seen,
            )
        )

    unique_pdfs = list(dict.fromkeys(pdf_links))[:PDF_URL_LIMIT]
    if fetch_pdfs and FETCH_PDFS and unique_pdfs:
        pdf_bundle = fetch_pdf_evidence(unique_pdfs)
        merged = merge_bundles(bundle, pdf_bundle)
        _replace(bundle, merged)

    remember_bundle(mpn, bundle)

    if is_error_url(bundle.mfr_url or ""):
        bundle.mfr_url = ""
    if not bundle.mfr_url and manufacturer_domains:
        bundle.mfr_url = best_mfr_url(mpn, manufacturer_domains)
    if is_error_url(bundle.mfr_url or ""):
        bundle.mfr_url = ""

    if bundle.items:
        save_cached_bundle(mpn, bundle)

    return bundle
