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
from extract.page_state import extract_page_state
from extract.confirm import confirm_desc_evidence
from extract.pdf_specs import extract_from_pdf_bytes, fetch_pdf_evidence
from extract.ref_discovery import discover_pdf_links, discover_product_links
from extract.structured import extract_structured_data
from sources.async_fetcher import fetch_all_pages, looks_like_js_shell
from sources.dead_paths import drop_dead_urls, note_outcome
from sources.learned_hosts import apply_run_lessons, learn_from_page
from sources.page_ok import is_error_url, is_not_found, is_usable_page, looks_like_empty_search, looks_like_pdf
from sources.finder import (
    best_mfr_url,
    candidate_distributor_urls,
    candidate_family_urls,
    candidate_mfr_urls,
    candidate_third_party_urls,
    first_fetch_window,
    is_blocked_url,
    is_pdf_url,
    is_search_url,
    looks_like_dealer_storefront,
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
from sources.wikidata import official_website_hosts
from sources.known_urls import known_urls_for, remember_bundle


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


def _manufacturer_settled(bundle: EvidenceBundle, mpn: str = "", mapped: bool = True) -> bool:
    """True when we already have manufacturer attributes on a real product page.

    Mapped brands can stop after that page. A guessed {name}.com homepage with
    two leftover spec strings must not skip web search for an unmapped brand.
    """
    if _needs_fallback(bundle) or not bundle.mfr_url:
        return False
    if is_search_url(bundle.mfr_url):
        return False
    if mapped:
        return True
    return official_url_score(bundle.mfr_url, mpn) >= 40


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
    prior: EvidenceBundle | None = None,
    names: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    if not is_allowed_url(url, manufacturer_domains) or is_error_url(url):
        return [], []
    if looks_like_pdf(html):
        try:
            page_bundle = extract_from_pdf_bytes(html.encode("latin-1", errors="replace"), url)
        except Exception:
            page_bundle = EvidenceBundle()
        learn_from_page(url, "", page_bundle, names)
        if is_blocked_url(url):
            return [], []
        apply_source_policy(page_bundle, url, manufacturer_domains)
        if page_bundle.items or page_bundle.approvals or page_bundle.warranty:
            merged = merge_bundles(bundle, page_bundle)
            _replace(bundle, merged)
        primary = is_primary_url(url, manufacturer_domains)
        if primary and official_url_score(url, mpn) >= official_url_score(bundle.mfr_url, mpn):
            bundle.mfr_url = url
        elif not is_search_url(url) and url not in bundle.ref_urls:
            bundle.ref_urls.append(url)
        return [], []
    products = discover_product_links(
        html,
        url,
        mpn,
        _follow_hosts(url, manufacturer_domains),
        limit=FOLLOW_URL_LIMIT,
    )
    pdfs = [
        link
        for link in discover_pdf_links(html, url)
        if is_primary_url(link, manufacturer_domains)
    ]
    query_search = "search?" in url.lower() or "search.html" in url.lower()
    primary = is_primary_url(url, manufacturer_domains)
    # Manufacturer listing/search pages: follow PDPs when we found them.
    # Empty "0 results" and JS search shells must not be ingested as specs.
    # That is not a reason to skip family / third-party / distributor pages.
    if is_search_url(url):
        if looks_like_empty_search(html):
            return [], pdfs
        if primary and products:
            save_raw_html(mpn, html, url)
            return products, pdfs
        if primary and query_search and not products:
            return [], pdfs
    save_raw_html(mpn, html, url)
    page_bundle = merge_bundles(
        extract_from_html(html, url),
        extract_structured_data(html, url),
        extract_page_state(html, url),
    )
    learn_from_page(url, html, page_bundle, names)
    if is_blocked_url(url):
        return products, pdfs
    apply_source_policy(page_bundle, url, manufacturer_domains)
    unreadable = primary and looks_like_js_shell(html) and not page_bundle.items
    contributed = (
        page_bundle.items
        or page_bundle.marketing
        or page_bundle.features
        or page_bundle.image_urls
        or page_bundle.approvals
        or page_bundle.product_ids
    )
    if contributed and not unreadable:
        merged = merge_bundles(bundle, page_bundle)
        _replace(bundle, merged)
    confirm_desc_evidence(bundle, html, url, manufacturer_domains)
    if prior is not None and prior is not bundle:
        confirm_desc_evidence(prior, html, url, manufacturer_domains)
    if primary and not is_search_url(url):
        if official_url_score(url, mpn) >= official_url_score(bundle.mfr_url, mpn):
            if (contributed and not unreadable) or official_url_score(url, mpn) >= 40:
                bundle.mfr_url = url
    elif contributed and not unreadable and url not in bundle.ref_urls:
        if not is_blocked_url(url) and not (primary and is_search_url(url)):
            bundle.ref_urls.append(url)
    return products, pdfs


def _handle_fetched_page(
    bundle: EvidenceBundle,
    status: int,
    html: str,
    final_url: str,
    requested: str,
    mpn: str,
    manufacturer_domains: list[str],
    seen: set[str],
    follow_urls: list[str],
    pdf_links: list[str],
    prior: EvidenceBundle | None,
    names: list[str] | None = None,
) -> None:
    note_outcome(requested, mpn, status, html, final_url)
    if is_not_found(status, html, final_url) or is_not_found(status, html, requested):
        from sources.known_urls import forget_urls

        forget_urls(mpn, [requested, final_url])
    if not is_usable_page(status, html, final_url):
        return
    products, pdfs = _ingest_page(
        bundle, html, final_url, mpn, manufacturer_domains, prior=prior, names=names
    )
    pdf_links.extend(pdfs)
    for product in products:
        if product not in seen and is_allowed_url(product, manufacturer_domains) and not is_error_url(product):
            seen.add(product)
            follow_urls.append(product)


def _fetch_tier(
    bundle: EvidenceBundle,
    start_urls: list[str],
    mpn: str,
    manufacturer_domains: list[str],
    seen: set[str],
    follow: bool = True,
    prior: EvidenceBundle | None = None,
    stop_when=None,
    names: list[str] | None = None,
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
    handled: list[str] = []

    def on_page(status, html, final_url, requested) -> bool:
        _handle_fetched_page(
            bundle,
            status,
            html,
            final_url,
            requested,
            mpn,
            manufacturer_domains,
            seen,
            follow_urls,
            pdf_links,
            prior,
            names=names,
        )
        handled.append(requested)
        return bool(stop_when and stop_when())

    pages = _run_coroutine_blocking(
        fetch_all_pages(start_urls, timeout=FETCH_TIMEOUT, on_page=on_page)
    )
    if not handled:
        for status, html, final_url, requested in pages:
            on_page(status, html, final_url, requested)

    if follow and follow_urls and not (stop_when and stop_when()):
        more_handled: list[str] = []

        def on_follow(status, html, final_url, requested) -> bool:
            _handle_fetched_page(
                bundle,
                status,
                html,
                final_url,
                requested,
                mpn,
                manufacturer_domains,
                seen,
                follow_urls,
                pdf_links,
                prior,
                names=names,
            )
            more_handled.append(requested)
            return bool(stop_when and stop_when())

        more = _run_coroutine_blocking(
            fetch_all_pages(follow_urls[:FOLLOW_URL_LIMIT], timeout=FETCH_TIMEOUT, on_page=on_follow)
        )
        if not more_handled:
            for status, html, final_url, requested in more:
                on_follow(status, html, final_url, requested)
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
    prior: EvidenceBundle | None = None,
) -> EvidenceBundle:
    bundle = EvidenceBundle()
    names = [name for name in (manufacturer_name, brand_name) if name]
    mapped_domains = list(domains or [])
    manufacturer_domains = list(mapped_domains)
    if not manufacturer_domains:
        wiki_hosts = official_website_hosts(names)
        guessed: list[str] = []
        for name in names:
            guessed.extend(guess_domains_from_name(name))
        manufacturer_domains = list(dict.fromkeys(wiki_hosts + guessed))
        if wiki_hosts:
            mapped_domains = list(wiki_hosts)
    url_limit = max_urls or FETCH_URL_LIMIT
    seen: set[str] = set()
    pdf_links: list[str] = []

    def settled() -> bool:
        return _manufacturer_settled(bundle, mpn, mapped=bool(mapped_domains))

    def fetch_tier(urls: list[str], follow: bool = True) -> list[str]:
        return _fetch_tier(
            bundle,
            urls,
            mpn,
            manufacturer_domains,
            seen,
            follow=follow,
            prior=prior,
            stop_when=settled,
            names=names,
        )

    known_primary, known_fallback = _split_known_urls(mpn, manufacturer_domains)
    known_pdfs = [url for url in known_primary + known_fallback if is_pdf_url(url)]
    known_primary = [url for url in known_primary if not is_pdf_url(url)]
    known_fallback = [url for url in known_fallback if not is_pdf_url(url)]
    pdf_links.extend(known_pdfs)
    if known_primary:
        manufacturer_domains = list(dict.fromkeys(manufacturer_domains + _hosts_from_urls(known_primary)))
        pdf_links.extend(fetch_tier(known_primary[:url_limit]))

    # Mapped brands: host product templates first. If those miss, web search
    # for a manufacturer PDP (that is how an unseen SKU on a new CMS path is
    # found). Family literature and distributors come after, not instead.
    # Unmapped brands: web search first so we do not spend the window on
    # {name}.com/p/{mpn} 404s before looking up the real host.
    if mapped_domains and not settled():
        pdf_links.extend(
            fetch_tier(first_fetch_window(candidate_mfr_urls(mpn, mapped_domains), url_limit))
        )
    need_search = (not mapped_domains) or _needs_fallback(bundle) or not bundle.mfr_url
    if settled():
        need_search = False
    if need_search:
        search_hits, extra_domains, found = _discover_search_urls(
            mpn,
            mapped_domains,
            seen,
            manufacturer_name=manufacturer_name,
            brand_name=brand_name,
        )
        if extra_domains:
            manufacturer_domains = list(dict.fromkeys(manufacturer_domains + extra_domains))
        if search_hits:
            pdf_links.extend(fetch_tier(search_hits))
    else:
        found = []

    if mapped_domains and not settled():
        pdf_links.extend(
            fetch_tier(candidate_family_urls(mpn, manufacturer_domains)[:SECONDARY_URL_LIMIT])
        )

    if not mapped_domains and manufacturer_domains and not settled():
        pdf_links.extend(
            fetch_tier(first_fetch_window(candidate_mfr_urls(mpn, manufacturer_domains), url_limit))
        )
        if not settled():
            pdf_links.extend(
                fetch_tier(candidate_family_urls(mpn, manufacturer_domains)[:SECONDARY_URL_LIMIT])
            )

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
            fetch_tier(
                list(dict.fromkeys(known_third + candidate_third_party_urls(mpn)[:THIRD_PARTY_URL_LIMIT] + third_hits))
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
            fetch_tier(
                list(dict.fromkeys(known_dist + candidate_distributor_urls(mpn)[:DISTRIBUTOR_URL_LIMIT] + dist_hits))
            )
        )

    unique_pdfs = list(dict.fromkeys(pdf_links))[:PDF_URL_LIMIT]
    if fetch_pdfs and FETCH_PDFS and unique_pdfs:
        pdf_bundle = fetch_pdf_evidence(unique_pdfs)
        merged = merge_bundles(bundle, pdf_bundle)
        _replace(bundle, merged)

    apply_run_lessons(bundle, names)
    remember_bundle(mpn, bundle)

    if is_error_url(bundle.mfr_url or "") or is_blocked_url(bundle.mfr_url or "") or looks_like_dealer_storefront(bundle.mfr_url or "") or is_search_url(bundle.mfr_url or ""):
        bundle.mfr_url = ""
    if not bundle.mfr_url and manufacturer_domains:
        bundle.mfr_url = best_mfr_url(mpn, manufacturer_domains)
    if is_error_url(bundle.mfr_url or "") or is_blocked_url(bundle.mfr_url or "") or looks_like_dealer_storefront(bundle.mfr_url or "") or is_search_url(bundle.mfr_url or ""):
        bundle.mfr_url = ""
    bundle.ref_urls = [
        url
        for url in bundle.ref_urls
        if url.startswith("http") and not is_blocked_url(url)
    ]

    if bundle.items:
        save_cached_bundle(mpn, bundle)

    return bundle
