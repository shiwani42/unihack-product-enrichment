import re

from bs4 import BeautifulSoup


def discover_pdf_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if ".pdf" not in href.lower():
            continue
        if href.startswith("http"):
            links.append(href)
        elif href.startswith("/"):
            match = re.match(r"^(https?://[^/]+)", base_url)
            if match:
                links.append(match.group(1) + href)
    return list(dict.fromkeys(links))


def discover_feature_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    features: list[str] = []
    for tag in soup.find_all(["li", "p", "span"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if not text or len(text) < 8 or len(text) > 120:
            continue
        if any(token in text.lower() for token in ("rack", "cycle", "dba", "rinse", "spray", "tines", "sensor")):
            if text not in features:
                features.append(text)
    return features[:20]


def discover_marketing_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for selector in ("meta",):
        for tag in soup.find_all(selector):
            if tag.get("name", "").lower() == "description":
                content = (tag.get("content") or "").strip()
                if len(content) > 40:
                    return content
    paragraphs: list[str] = []
    for tag in soup.find_all("p"):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if len(text) > 60 and "dishwasher" in text.lower():
            paragraphs.append(text)
    return paragraphs[0] if paragraphs else ""
