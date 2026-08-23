"""Decide whether a fetched page is usable evidence or a miss (404 / soft 404)."""

from __future__ import annotations

import re

_ERROR_URL_MARKERS = (
    "/error-pages/",
    "/404",
    "page-not-found",
    "/not-found",
    "/errors/",
    "pagenotfound",
    "errorpage",
    "404.html",
    "404.htm",
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TITLE_MISS = ("404", "not found", "page not found", "error 404", "doesn't exist", "does not exist")
_EMPTY_SEARCH = re.compile(
    r"0 results|no results found|no products found|did not match any|no matches",
    re.I,
)


def is_error_url(url: str) -> bool:
    low = (url or "").lower()
    if not low.startswith(("http://", "https://")):
        return False
    return any(marker in low for marker in _ERROR_URL_MARKERS)


def looks_like_error_html(html: str) -> bool:
    if not html:
        return False
    match = _TITLE.search(html[:6000])
    if not match:
        return False
    title = re.sub(r"\s+", " ", match.group(1)).strip().lower()
    return any(token in title for token in _TITLE_MISS)


def is_not_found(status: int, html: str, url: str) -> bool:
    """HTTP 404/410 or a soft 404 (redirect/title). Network failures are not this."""
    if is_error_url(url):
        return True
    if status in (404, 410):
        return True
    if 200 <= status < 400 and looks_like_error_html(html or ""):
        return True
    return False


def looks_like_empty_search(html: str) -> bool:
    """True when an on-site search page says it found nothing."""
    text = html or ""
    if not text.strip():
        return False
    visible = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    visible = re.sub(r"<style[^>]*>.*?</style>", " ", visible, flags=re.I | re.S)
    visible = re.sub(r"<[^>]+>", " ", visible)
    return bool(_EMPTY_SEARCH.search(visible[:8000]))


def looks_like_pdf(html: str) -> bool:
    """True when a fetched body is a PDF, even if the URL has no .pdf suffix."""
    raw = html or ""
    if raw.lstrip().startswith("%PDF"):
        return True
    head = raw[:64]
    if head.count("\x00") >= 2:
        return True
    return False


def is_usable_page(status: int, html: str, url: str) -> bool:
    if status < 200 or status >= 400:
        return False
    if not (html or "").strip():
        return False
    if is_not_found(status, html, url):
        return False
    return True
