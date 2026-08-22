import io
import re
import time
from typing import Iterable

import httpx
import pdfplumber

from app.config import PDF_MAX_BYTES, REQUEST_TIMEOUT, USER_AGENT
from extract.evidence import Evidence, EvidenceBundle

SPEC_PAGE_KEYWORDS = (
    "specification",
    "electrical",
    "dimensions",
    "product data",
    "technical",
    "ratings",
)

HEADERS = {"User-Agent": USER_AGENT}


def _pdf_request(client: httpx.Client, url: str, method: str) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            if method == "head":
                return client.head(url)
            return client.get(url)
        except httpx.HTTPError as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def _score_page(text: str) -> int:
    lowered = text.lower()
    score = 0
    for keyword in SPEC_PAGE_KEYWORDS:
        if keyword in lowered:
            score += 2
    for token in ("120 v", "voltage", "amperage", "dba", "inches", "in.", "mounting"):
        if token in lowered:
            score += 1
    return score


def find_spec_pages(pdf: pdfplumber.PDF) -> list[int]:
    scored: list[tuple[int, int]] = []
    for index, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        score = _score_page(text)
        if score > 0:
            scored.append((score, index))
    scored.sort(reverse=True)
    if not scored:
        return list(range(min(5, len(pdf.pages))))
    return [index for _, index in scored[:8]]


def _set_field(bundle: EvidenceBundle, field: str, value: str, uom: str, url: str, quote: str) -> None:
    if not value:
        return
    bundle.set(
        Evidence(
            field=field,
            value=value,
            uom=uom,
            source_url=url,
            quote=quote[:180],
            extractor="pdf_regex",
            confidence=0.85,
        )
    )


def extract_from_text(text: str, url: str, bundle: EvidenceBundle) -> None:
    patterns: list[tuple[str, str, str]] = [
        ("Series", r"(Professional Series|Eco Series|Gallery Series)", ""),
        ("Number of Wash Cycles", r"(?:Number of Wash Cycles|Wash Cycles?)\s*[:\-]?\s*(\d+)", ""),
        ("Voltage Rating", r"(?:Voltage Rating|Rated Voltage|120\s*Volts?)\s*[:\-]?\s*(\d{2,3})", "V"),
        ("Amperage Rating", r"(?:Amperage Rating|Amps? @ 120 Volts?|Current)\s*[:\-]?\s*(\d{1,2})", "A"),
        ("Mounting Type", r"(?:Mounting Type|Mounting)\s*[:\-]?\s*(Leg|Built[- ]in)", ""),
        ("Sound Level", r"(\d{2})\s*dBA", "dBA"),
        ("Material", r"(Stainless Steel)", ""),
        ("Color", r"(?:Color|Finish)\s*[:\-]?\s*(Stainless Steel|Black|White)", ""),
        (
            "Size",
            r"(\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*H\s*x\s*\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*W\s*x\s*\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*D)",
            "",
        ),
        ("Depth With Door Open", r"Depth With Door Open\s*[:\-]?\s*(\d{1,2}-?\d{0,2}/\d{0,2})", "in"),
        ("Minimum Height", r"Minimum Height\s*[:\-]?\s*(\d{1,2}-?\d{0,2}/\d{0,2})", "in"),
    ]
    for field, pattern, uom in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = match.group(1).strip()
        if field == "Mounting Type" and value.lower().replace("-", " ") == "built in":
            value = "Built-in"
        _set_field(bundle, field, value, uom, url, match.group(0))

    approvals = re.findall(
        r"(ASSE \d+|CEE Tier \d+ Qualified|cUL Listed|ENERGY STAR Certified|NSF Certified|UL Listed)",
        text,
        re.I,
    )
    if approvals:
        bundle.approvals = "|".join(dict.fromkeys(approval.replace("Cul", "cUL") for approval in approvals))

    warranty_match = re.search(
        r"(\d+\s*Year\s+Manufacturer,\s*\d+\s*Year\s+Labor and Parts)",
        text,
        re.I,
    )
    if warranty_match:
        bundle.warranty = warranty_match.group(1)


def extract_from_pdf_bytes(content: bytes, url: str) -> EvidenceBundle:
    bundle = EvidenceBundle()
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        pages = find_spec_pages(pdf)
        combined = "\n".join((pdf.pages[i].extract_text() or "") for i in pages)
        extract_from_text(combined, url, bundle)
    return bundle


def fetch_pdf_evidence(urls: Iterable[str]) -> EvidenceBundle:
    bundle = EvidenceBundle()
    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
        for url in urls:
            if not url.lower().endswith(".pdf"):
                continue
            try:
                head = _pdf_request(client, url, "head")
                size = int(head.headers.get("content-length", "0") or 0)
                if size and size > PDF_MAX_BYTES:
                    continue
                response = _pdf_request(client, url, "get")
                if response.status_code >= 400 or not response.content:
                    continue
                page_bundle = extract_from_pdf_bytes(response.content, str(response.url))
                bundle.ref_urls.append(str(response.url))
                for item in page_bundle.items:
                    bundle.set(item)
                if page_bundle.approvals:
                    bundle.approvals = page_bundle.approvals
                if page_bundle.warranty:
                    bundle.warranty = page_bundle.warranty
            except (httpx.HTTPError, OSError, ValueError):
                continue
    return bundle
