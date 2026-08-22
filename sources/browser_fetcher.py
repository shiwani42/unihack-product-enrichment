import httpx

from app.config import REQUEST_TIMEOUT, USER_AGENT

HEADERS = {"User-Agent": USER_AGENT}


def fetch_html(url: str) -> tuple[int, str, str]:
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
            response = client.get(url)
            return response.status_code, response.text, str(response.url)
    except httpx.HTTPError:
        return 0, "", url


def fetch_html_with_browser(url: str) -> tuple[int, str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 0, "", url

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            content = page.content()
            final_url = page.url
            browser.close()
            return 200, content, final_url
    except Exception:
        return 0, "", url


def fetch_page(url: str) -> tuple[int, str, str]:
    status, html, final_url = fetch_html(url)
    if status == 403 or not html:
        status, html, final_url = fetch_html_with_browser(url)
    return status, html, final_url
