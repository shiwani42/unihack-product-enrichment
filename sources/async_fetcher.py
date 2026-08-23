"""Async HTTP fetch with tiered fallback, retry/backoff and bounded concurrency."""

import asyncio
import contextlib
import os
import re

import httpx

from app.config import FETCH_CONNECT_TIMEOUT, FETCH_TIMEOUT, HTTP_RETRY_ATTEMPTS, HTTP_RETRY_BASE_DELAY
from sources.browser_fetcher import fetch_html_with_browser
from sources.finder import is_blocked_url, is_search_url
from sources.page_ok import is_usable_page
from sources.retry import RETRYABLE_STATUS
from sources.web_search import BROWSER_HEADERS

HEADERS = BROWSER_HEADERS
MAX_CONCURRENT_FETCHES = 8
_semaphores: dict[int, asyncio.Semaphore] = {}


async def _reject_shopping(request: httpx.Request) -> None:
    # httpx 0.28 awaits request hooks. A sync hook raises TypeError and every
    # manufacturer fetch is swallowed by fetch_all_pages(return_exceptions=True).
    if is_blocked_url(str(request.url)):
        raise httpx.RequestError("blocked shopping host", request=request)


def _semaphore() -> asyncio.Semaphore:
    loop_id = id(asyncio.get_running_loop())
    semaphore = _semaphores.get(loop_id)
    if semaphore is None:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
        _semaphores[loop_id] = semaphore
    return semaphore


def _timeout(read: int) -> httpx.Timeout:
    return httpx.Timeout(
        connect=FETCH_CONNECT_TIMEOUT,
        read=float(read),
        write=5.0,
        pool=2.0,
    )


def _http_client(timeout: int, ipv4: bool) -> httpx.AsyncClient:
    kwargs: dict = {
        "timeout": _timeout(timeout),
        "follow_redirects": True,
        "headers": HEADERS,
        "event_hooks": {"request": [_reject_shopping]},
    }
    if ipv4:
        try:
            kwargs["transport"] = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        except OSError:
            pass
    return httpx.AsyncClient(**kwargs)


def looks_like_js_shell(html: str) -> bool:
    """True when the response is a script-heavy shell with almost no visible specs."""
    raw = html or ""
    if len(raw) < 12000:
        return False
    lowered = raw.lower()
    if 'id="__next_data__"' in lowered or "id='__next_data__'" in lowered:
        return False
    if lowered.count("<script") < 8:
        return False
    visible = re.sub(r"<script[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    visible = re.sub(r"<style[^>]*>.*?</style>", " ", visible, flags=re.I | re.S)
    visible = re.sub(r"<[^>]+>", " ", visible)
    visible = re.sub(r"\s+", " ", visible).strip()
    return len(visible) < 500


def _playwright_allowed(url: str) -> bool:
    if os.environ.get("VERCEL"):
        return False
    if os.environ.get("UNILOG_PLAYWRIGHT", "1").strip().lower() in {"0", "false", "no"}:
        return False
    return not is_search_url(url)


async def fetch_html_async(
    url: str,
    timeout: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[int, str, str]:
    if is_blocked_url(url):
        return 0, "", url

    request_timeout = timeout or FETCH_TIMEOUT
    attempts = max(1, HTTP_RETRY_ATTEMPTS)

    async def _get(http: httpx.AsyncClient) -> tuple[int, str, str]:
        last_status, last_html, last_final = 0, "", url
        for attempt in range(attempts):
            try:
                response = await http.get(url)
            except httpx.HTTPError:
                if attempt < attempts - 1:
                    await asyncio.sleep(HTTP_RETRY_BASE_DELAY * (2**attempt))
                    continue
                return last_status, last_html, last_final
            final_url = str(response.url)
            if is_blocked_url(final_url):
                return 0, "", url
            last_status, last_html, last_final = response.status_code, response.text, final_url
            if response.status_code < 400 or response.status_code not in RETRYABLE_STATUS:
                return last_status, last_html, last_final
            if attempt < attempts - 1:
                await asyncio.sleep(HTTP_RETRY_BASE_DELAY * (2**attempt))
        return last_status, last_html, last_final

    async with _semaphore():
        if client is not None:
            return await _get(client)
        last = (0, "", url)
        for ipv4 in (True, False):
            async with _http_client(request_timeout, ipv4) as owned:
                last = await _get(owned)
            if last[0]:
                return last
        return last


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

    request_timeout = timeout or FETCH_TIMEOUT
    browser_left = 1
    browser_lock = asyncio.Lock()

    async def _maybe_browser(url: str, status: int, html: str, final: str) -> tuple[int, str, str]:
        nonlocal browser_left
        if not _playwright_allowed(url):
            return status, html, final
        if status != 403 and not (status == 200 and looks_like_js_shell(html)):
            return status, html, final
        async with browser_lock:
            if browser_left <= 0:
                return status, html, final
            browser_left -= 1
        return await asyncio.to_thread(fetch_html_with_browser, url, request_timeout)

    async def _one(client: httpx.AsyncClient, url: str) -> tuple[int, str, str, str]:
        status, html, final = await fetch_html_async(url, timeout=request_timeout, client=client)
        if is_blocked_url(final):
            return 0, "", url, url
        status, html, final = await _maybe_browser(url, status, html, final)
        return status, html, final, url

    async def _batch(subset: list[str], ipv4: bool) -> dict[str, tuple[int, str, str, str]]:
        async with _http_client(request_timeout, ipv4) as client:
            gathered = await asyncio.gather(*[_one(client, url) for url in subset], return_exceptions=True)
        out: dict[str, tuple[int, str, str, str]] = {}
        for url, item in zip(subset, gathered):
            if isinstance(item, Exception):
                out[url] = (0, "", url, url)
            else:
                out[url] = item
        return out

    by_url = await _batch(urls, ipv4=True)
    misses = [url for url, page in by_url.items() if page[0] == 0 and page[1] == ""]
    if misses:
        recovered = await _batch(misses, ipv4=False)
        by_url.update(recovered)
    return [by_url[url] for url in urls]


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
