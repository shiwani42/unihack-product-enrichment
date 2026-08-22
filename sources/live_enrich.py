"""Dynamic manufacturer fetch: domains + MPN only, no per-SKU hardcoding."""

import asyncio
import concurrent.futures

from app.config import FETCH_TIMEOUT, FETCH_URL_LIMIT
from extract.cache import load_cached_bundle, save_cached_bundle
from extract.html_specs import extract_from_html
from extract.merge import merge_bundles
from extract.pdf_specs import fetch_pdf_evidence
from extract.ref_discovery import discover_pdf_links
from extract.structured import extract_structured_data
from extract.evidence import EvidenceBundle
from sources.async_fetcher import fetch_urls_parallel
from sources.finder import best_mfr_url, candidate_mfr_urls, is_blocked_url
from sources.raw_cache import save_raw_html

CACHE_HIT_THRESHOLD = 5
CACHE_SAVE_THRESHOLD = 3


def _run_coroutine_blocking(coroutine):
    """Run a coroutine to completion from sync code, even inside a running loop.

    ``asyncio.run`` raises when the calling thread already has an event loop
    (FastAPI async endpoints). In that case run an isolated loop on a worker
    thread so callers never have to care which context they're in.
    """
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


def fetch_manufacturer_evidence(
    mpn: str,
    domains: list[str],
    max_urls: int | None = None,
    fetch_pdfs: bool = True,
) -> EvidenceBundle:
    cached = load_cached_bundle(mpn)
    if cached and len(cached.items) >= CACHE_HIT_THRESHOLD:
        return cached

    bundle = EvidenceBundle()
    if cached:
        bundle = merge_bundles(bundle, cached)

    if not domains:
        url = bundle.mfr_url or best_mfr_url(mpn, domains)
        if url and not bundle.mfr_url:
            bundle.mfr_url = url
        return bundle

    url_limit = max_urls or FETCH_URL_LIMIT
    urls = [u for u in candidate_mfr_urls(mpn, domains) if not is_blocked_url(u)][:url_limit]
    pdf_links: list[str] = list(bundle.ref_urls)

    if urls:
        status, html, final_url = _run_coroutine_blocking(
            fetch_urls_parallel(urls, timeout=FETCH_TIMEOUT)
        )
        if status < 400 and html:
            save_raw_html(mpn, html, final_url)
            page_bundle = extract_from_html(html, final_url)
            structured = extract_structured_data(html, final_url)
            page_bundle = merge_bundles(page_bundle, structured)
            bundle.product_ids.update(structured.product_ids)
            if page_bundle.items or page_bundle.marketing or page_bundle.features:
                bundle = merge_bundles(bundle, page_bundle)
                bundle.mfr_url = final_url
                pdf_links.extend(discover_pdf_links(html, final_url))

    if fetch_pdfs and pdf_links:
        pdf_bundle = fetch_pdf_evidence(dict.fromkeys(pdf_links))
        bundle = merge_bundles(bundle, pdf_bundle)

    if not bundle.mfr_url:
        bundle.mfr_url = best_mfr_url(mpn, domains)

    if len(bundle.items) >= CACHE_SAVE_THRESHOLD:
        save_cached_bundle(mpn, bundle)

    return bundle
