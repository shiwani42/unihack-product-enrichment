import re

import httpx

from app.config import REQUEST_TIMEOUT, USER_AGENT
from extract.evidence import Evidence, EvidenceBundle
from sources.finder import candidate_mfr_urls, is_blocked_url


HEADERS = {"User-Agent": USER_AGENT}


def _clean_text(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def _extract_labeled_value(text: str, label: str) -> tuple[str, str]:
    pattern = rf"{re.escape(label)}\s*[:\-]?\s*([0-9][0-9,\./\-\s]*)\s*([A-Za-z%]+)?"
    match = re.search(pattern, text, re.I)
    if not match:
        return "", ""
    value = match.group(1).strip()
    uom = (match.group(2) or "").strip()
    return value, uom


def extract_from_html(html: str, url: str) -> EvidenceBundle:
    bundle = EvidenceBundle(mfr_url=url)
    text = _clean_text(html)

    patterns = {
        "Series": r"(Professional Series|Eco Series|Gallery Series)",
        "Number of Wash Cycles": r"(\d+)\s*(?:Wash Cycles|wash cycles)",
        "Voltage Rating": r"(?:Voltage Rating|Amps @ 120 Volts|120\s*Volts)[^\d]*([0-9]{2,3})\s*V?",
        "Amperage Rating": r"(?:Amperage Rating|Amps @ 120 Volts)[^\d]*([0-9]{1,2})\s*A?",
        "Mounting Type": r"(Leg|Built-in|Built in)",
        "Sound Level": r"(\d{2})\s*dBA",
        "Material": r"(Stainless Steel)",
        "Color": r"Color\s*[:\-]?\s*(Stainless Steel|Black|White)",
        "Depth With Door Open": r"Depth With Door Open[^\d]*([0-9][0-9,\./\-\s]+)\s*in",
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = match.group(1).strip()
        if field == "Mounting Type":
            if value.lower().replace("-", " ") == "built in":
                value = "Built-in"
            elif value.lower() == "leg":
                value = "Leg"
        uom = ""
        if field in {"Voltage Rating"}:
            uom = "V"
        elif field in {"Amperage Rating"}:
            uom = "A"
        elif field in {"Sound Level"}:
            uom = "dBA"
        elif field in {"Depth With Door Open"}:
            uom = "in"
        bundle.set(
            Evidence(
                field=field,
                value=value,
                uom=uom,
                source_url=url,
                quote=match.group(0)[:180],
                extractor="html_regex",
                confidence=0.75,
            )
        )

    with_match = re.search(r"With\s+([^\.]{3,80})", text, re.I)
    if with_match:
        bundle.set(
            Evidence(
                field="With",
                value=f"With {with_match.group(1).strip()}",
                source_url=url,
                quote=with_match.group(0)[:180],
                extractor="html_regex",
                confidence=0.7,
            )
        )

    return bundle


def fetch_evidence(mpn: str, domains: list[str]) -> EvidenceBundle:
    bundle = EvidenceBundle()
    for url in candidate_mfr_urls(mpn, domains):
        if is_blocked_url(url):
            continue
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
                response = client.get(url)
                if response.status_code >= 400:
                    continue
                page_bundle = extract_from_html(response.text, str(response.url))
                if page_bundle.items:
                    bundle = page_bundle
                    break
        except httpx.HTTPError:
            continue
    return bundle
