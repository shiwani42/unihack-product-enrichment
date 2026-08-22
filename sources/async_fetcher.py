"""Async HTTP fetch with tiered fallback, retry/backoff and bounded concurrency."""

import asyncio
import contextlib

import httpx

from app.config import FETCH_TIMEOUT, USER_AGENT
from sources.browser_fetcher import fetch_html_with_browser
from sources.retry import RETRYABLE_STATUS

HEADERS = {"User-Agent": USER_AGENT}
MAX_CONCURRENT_FETCHES = 8
_semaphores: dict[int, asyncio.Semaphore] = {}


def _semaphore() -> asyncio.Semaphore:
    loop_id = id(asyncio.get_running_loop())
    semaphore = _semaphores.get(loop_id)
    if semaphore is None:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
        _semaphores[loop_id] = semaphore
    return semaphore


async def fetch_html_async(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    request_timeout = timeout or FETCH_TIMEOUT
    async with _semaphore():
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=request_timeout,
                    follow_redirects=True,
                    headers=HEADERS,
                ) as client:
                    response = await client.get(url)
            except httpx.HTTPError:
                return 0, "", url
            if response.status_code < 400 or response.status_code not in RETRYABLE_STATUS:
                return response.status_code, response.text, str(response.url)
            if attempt < 1:
                await asyncio.sleep(0.5 * (2**attempt))
        return response.status_code, response.text, str(response.url)


async def fetch_urls_parallel(
    urls: list[str],
    timeout: int | None = None,
) -> tuple[int, str, str]:
    if not urls:
        return 0, "", ""

    async def _one(url: str) -> tuple[int, str, str]:
        status, html, final = await fetch_html_async(url, timeout=timeout)
        if status == 403 or (status >= 400 and not html):
            return await asyncio.to_thread(fetch_html_with_browser, url, timeout)
        return status, html, final

    tasks = [asyncio.create_task(_one(url)) for url in urls]
    try:
        for coro in asyncio.as_completed(tasks):
            status, html, final_url = await coro
            if status < 400 and html:
                return status, html, final_url
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
    return 0, "", urls[0]
