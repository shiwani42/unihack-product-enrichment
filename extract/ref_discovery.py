import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from sources.finder import is_blocked_url, url_on_domains

_PDF_URL_RE = re.compile(r"https?://[^\s\"'<>]+?\.pdf", re.I)
_DOC_TEXT = (
    "owner", "manual", "install", "specification", "spec sheet",
    "dimension", "warranty", "energy guide", "quick start", "cycle guide",
)


def _absolute(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    return urljoin(base_url, href)


def _is_document_url(url: str) -> bool:
    low = url.lower()
    if is_blocked_url(url):
        return False
    if any(ext in low for ext in (".png", ".jpg", ".jpeg", ".gif", ".tif", ".svg", ".webp")):
        return False
    return ".pdf" in low


def discover_pdf_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        url = _absolute(anchor["href"], base_url)
        if _is_document_url(url):
            links.append(url)
        else:
            text = " ".join(anchor.get_text(" ", strip=True).split()).lower()
            if ".pdf" not in url.lower() and any(token in text for token in _DOC_TEXT) and url.lower().endswith(".pdf"):
                links.append(url)
    for match in _PDF_URL_RE.findall(html or ""):
        url = match.rstrip(").,;]")
        if _is_document_url(url):
            links.append(url)
    return list(dict.fromkeys(links))


def discover_product_links(html: str, base_url: str, mpn: str, domains: list[str], limit: int = 6) -> list[str]:
    """Follow official product/support hits that stay on allowed hosts."""
    soup = BeautifulSoup(html, "lxml")
    needle = mpn.lower()
    found: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        url = _absolute(href, base_url)
        if is_blocked_url(url) or url.lower().endswith(".pdf"):
            continue
        if not url_on_domains(url, domains):
            continue
        path = urlparse(url).path.lower()
        text = " ".join(anchor.get_text(" ", strip=True).split()).lower()
        compact = needle.replace("-", "")
        official = any(token in url.lower() for token in ("owner-center", "product-support", "gea-specs", "smartsearch", "/appliance/"))
        if needle not in url.lower() and needle not in text and compact not in path.replace("-", "") and not official:
            continue
        if url not in found:
            found.append(url)
        if len(found) >= limit:
            break
    return found


def discover_feature_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    features: list[str] = []
    tokens = (
        "rack", "cycle", "dba", "rinse", "spray", "tines", "sensor",
        "volt", "amp", "watt", "rpm", "diameter", "warranty", "spec",
        "dimension", "stainless", "grit",
    )
    for tag in soup.find_all(["li", "p", "span"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if not text or len(text) < 8 or len(text) > 120:
            continue
        lowered = text.lower()
        if any(token in lowered for token in tokens):
            if text not in features:
                features.append(text)
    return features[:20]


def discover_marketing_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("meta"):
        if tag.get("name", "").lower() == "description":
            content = (tag.get("content") or "").strip()
            if len(content) > 40:
                return content
    paragraphs: list[str] = []
    for tag in soup.find_all("p"):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if len(text) > 60:
            paragraphs.append(text)
    return paragraphs[0] if paragraphs else ""
