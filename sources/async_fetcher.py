"""Async HTTP fetch with tiered fallback, retry/backoff and bounded concurrency."""

import asyncio
import contextlib

import httpx

from app.config import FETCH_TIMEOUT
from sources.browser_fetcher import fetch_html_with_browser
from sources.finder import is_blocked_url
from sources.page_ok import is_usable_page
from sources.retry import RETRYABLE_STATUS
from sources.web_search import BROWSER_HEADERS

HEADERS = BROWSER_HEADERS
MAX_CONCURRENT_FETCHES = 8
_semaphores: dict[int, asyncio.Semaphore] = {}


def _reject_shopping(request: httpx.Request) -> None:
    if is_blocked_url(str(request.url)):
        raise httpx.RequestError("blocked shopping host", request=request)


def _semaphore() -> asyncio.Semaphore:
    loop_id = id(asyncio.get_running_loop())
    semaphore = _semaphores.get(loop_id)
    if semaphore is None:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
        _semaphores[loop_id] = semaphore
    return semaphore


async def fetch_html_async(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    if is_blocked_url(url):
        return 0, "", url

    request_timeout = timeout or FETCH_TIMEOUT
    async with _semaphore():
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=request_timeout,
                    follow_redirects=True,
                    headers=HEADERS,
                    event_hooks={"request": [_reject_shopping]},
                ) as client:
                    response = await client.get(url)
            except httpx.HTTPError:
                return 0, "", url
            final_url = str(response.url)
            if is_blocked_url(final_url):
                return 0, "", url
            if response.status_code < 400 or response.status_code not in RETRYABLE_STATUS:
                return response.status_code, response.text, final_url
            if attempt < 1:
                await asyncio.sleep(0.5 * (2**attempt))
        return response.status_code, response.text, str(response.url)


async def fetch_urls_parallel(
    urls: list[str],
    timeout: int | None = None,
) -> tuple[int, str, str]:
    urls = [url for url in urls if not is_blocked_url(url)]
    if not urls:
        return 0, "", ""

    async def _one(url: str) -> tuple[int, str, str]:
        status, html, final = await fetch_html_async(url, timeout=timeout)
        if is_blocked_url(final):
            return 0, "", url
        if status == 403 or (status >= 400 and not html):
            return await asyncio.to_thread(fetch_html_with_browser, url, timeout)
        return status, html, final

    tasks = [asyncio.create_task(_one(url)) for url in urls]
    try:
        for coro in asyncio.as_completed(tasks):
            status, html, final_url = await coro
            if is_usable_page(status, html, final_url) and not is_blocked_url(final_url):
                return status, html, final_url
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
    return 0, "", urls[0]


async def fetch_all_pages(
    urls: list[str],
    timeout: int | None = None,
) -> list[tuple[int, str, str, str]]:
    """Fetch every allowed URL. Returns (status, html, final_url, requested)."""
    urls = [url for url in urls if not is_blocked_url(url)]
    if not urls:
        return []

    async def _one(url: str) -> tuple[int, str, str, str]:
        status, html, final = await fetch_html_async(url, timeout=timeout)
        if is_blocked_url(final):
            return 0, "", url, url
        if status == 403 or (status >= 400 and not html):
            status, html, final = await asyncio.to_thread(fetch_html_with_browser, url, timeout)
        return status, html, final, url

    gathered = await asyncio.gather(*[_one(url) for url in urls], return_exceptions=True)
    pages: list[tuple[int, str, str, str]] = []
    for item in gathered:
        if isinstance(item, Exception):
            continue
        pages.append(item)
    return pages


async def fetch_all_successful(
    urls: list[str],
    timeout: int | None = None,
) -> list[tuple[int, str, str]]:
    """Fetch allowed URLs; shopping hosts and 404/soft-404 pages are dropped."""
    pages: list[tuple[int, str, str]] = []
    for status, html, final_url, _requested in await fetch_all_pages(urls, timeout=timeout):
        if is_usable_page(status, html, final_url) and not is_blocked_url(final_url):
            pages.append((status, html, final_url))
    return pages
