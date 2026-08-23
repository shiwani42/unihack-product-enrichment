import httpx

from app.config import FETCH_CONNECT_TIMEOUT, REQUEST_TIMEOUT
from sources.finder import is_blocked_url
from sources.retry import call_with_retry
from sources.web_search import BROWSER_HEADERS

HEADERS = BROWSER_HEADERS


def _client_timeout(request_timeout: int) -> httpx.Timeout:
    return httpx.Timeout(
        connect=FETCH_CONNECT_TIMEOUT,
        read=float(request_timeout),
        write=5.0,
        pool=2.0,
    )


def _get_once(url: str, request_timeout: int) -> tuple[int, str, str]:
    if is_blocked_url(url):
        return 0, "", url
    try:
        with httpx.Client(timeout=_client_timeout(request_timeout), follow_redirects=True, headers=HEADERS) as client:
            response = client.get(url)
            final_url = str(response.url)
            if is_blocked_url(final_url):
                return 0, "", url
            return response.status_code, response.text, final_url
    except httpx.HTTPError:
        return 0, "", url


def fetch_html(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    if is_blocked_url(url):
        return 0, "", url
    request_timeout = timeout or REQUEST_TIMEOUT
    status, html, final_url = call_with_retry(lambda: _get_once(url, request_timeout))
    if is_blocked_url(final_url):
        return 0, "", url
    return status, html, final_url


def fetch_html_with_browser(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    if is_blocked_url(url):
        return 0, "", url
    request_timeout = timeout or REQUEST_TIMEOUT
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0, "", url

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=HEADERS["User-Agent"])
                page.goto(url, wait_until="domcontentloaded", timeout=request_timeout * 1000)
                content = page.content()
                final_url = page.url
                if is_blocked_url(final_url):
                    return 0, "", url
                return 200, content, final_url
            finally:
                browser.close()
    except Exception:
        return 0, "", url


def fetch_page(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    if is_blocked_url(url):
        return 0, "", url
    status, html, final_url = fetch_html(url, timeout=timeout)
    if is_blocked_url(final_url):
        return 0, "", url
    if status == 403 or not html:
        status, html, final_url = fetch_html_with_browser(url, timeout=timeout)
    if is_blocked_url(final_url):
        return 0, "", url
    return status, html, final_url
