import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from sources.finder import is_blocked_url, url_on_domains

_PDF_URL_RE = re.compile(r"https?://[^\s\"'<>]+?\.pdf", re.I)
_SHOPIFY_META = re.compile(
    r"var\s+meta\s*=\s*(\{.*?\})\s*;\s*for\s*\(\s*var\s+attr",
    re.S,
)
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


def shopify_product_urls(html: str, base_url: str, mpn: str) -> list[str]:
    """Shopify search/PDP pages hide handles in ShopifyAnalytics.meta, not in <a href>.

    Variant SKU 59243 lives on /products/{handle}, not /products/59243 (that 404s).
    """
    raw = (html or "")
    needle = (mpn or "").strip().lower()
    if not raw or not needle:
        return []
    match = _SHOPIFY_META.search(raw)
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        return []
    origin = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}" if "://" in (base_url or "") else base_url
    found: list[str] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        handle = str(product.get("handle") or "").strip().strip("/")
        if not handle:
            continue
        variants = product.get("variants") if isinstance(product.get("variants"), list) else []
        skus = [str(item.get("sku") or "").strip().lower() for item in variants if isinstance(item, dict)]
        if needle not in skus:
            continue
        url = _absolute(f"/products/{handle}", origin or base_url)
        if url not in found:
            found.append(url)
    return found


_SKIP_FOLLOW = (
    "login",
    "logout",
    "signin",
    "sign-in",
    "/cart",
    "/account",
    "wishlist",
    "/api/auth",
    "lwfilters",
)


def discover_product_links(html: str, base_url: str, mpn: str, domains: list[str], limit: int = 6) -> list[str]:
    """Follow official product/support hits that stay on allowed hosts."""
    found: list[str] = []
    for url in shopify_product_urls(html, base_url, mpn):
        if is_blocked_url(url) or not url_on_domains(url, domains):
            continue
        if url not in found:
            found.append(url)
        if len(found) >= limit:
            return found
    if found:
        return found
    soup = BeautifulSoup(html, "lxml")
    needle = mpn.lower()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        url = _absolute(href, base_url)
        low = url.lower()
        if is_blocked_url(url) or low.endswith(".pdf"):
            continue
        if any(token in low for token in _SKIP_FOLLOW):
            continue
        if not url_on_domains(url, domains):
            continue
        path = urlparse(url).path.lower()
        text = " ".join(anchor.get_text(" ", strip=True).split()).lower()
        compact = needle.replace("-", "")
        official = any(token in low for token in ("owner-center", "product-support", "gea-specs", "/appliance/"))
        if needle not in low and needle not in text and compact not in path.replace("-", "") and not official:
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
