import httpx

from app.config import REQUEST_TIMEOUT, USER_AGENT
from sources.retry import call_with_retry

HEADERS = {"User-Agent": USER_AGENT}


def _get_once(url: str, request_timeout: int) -> tuple[int, str, str]:
    try:
        with httpx.Client(timeout=request_timeout, follow_redirects=True, headers=HEADERS) as client:
            response = client.get(url)
            return response.status_code, response.text, str(response.url)
    except httpx.HTTPError:
        return 0, "", url


def fetch_html(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    request_timeout = timeout or REQUEST_TIMEOUT
    return call_with_retry(lambda: _get_once(url, request_timeout))


def fetch_html_with_browser(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    request_timeout = timeout or REQUEST_TIMEOUT
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0, "", url

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, wait_until="domcontentloaded", timeout=request_timeout * 1000)
                content = page.content()
                final_url = page.url
                return 200, content, final_url
            finally:
                browser.close()
    except Exception:
        return 0, "", url


def fetch_page(url: str, timeout: int | None = None) -> tuple[int, str, str]:
    status, html, final_url = fetch_html(url, timeout=timeout)
    if status == 403 or not html:
        status, html, final_url = fetch_html_with_browser(url, timeout=timeout)
    return status, html, final_url
