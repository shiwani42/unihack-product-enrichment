import json
import re
from html import unescape
from pathlib import Path

from extract.evidence import Evidence, EvidenceBundle
from extract.labeled_specs import extract_labeled_specs
from extract.ref_discovery import discover_feature_lines, discover_marketing_text

PATTERNS_PATH = Path(__file__).resolve().parent / "spec_patterns.json"


def _load_patterns() -> list[tuple[str, str, str, float]]:
    if not PATTERNS_PATH.exists():
        return []
    payload = json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
    return [(item["field"], item["pattern"], item.get("uom", ""), item.get("confidence", 0.75)) for item in payload]


def _clean_text(html: str) -> str:
    text = unescape(html or "")
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def _set(bundle: EvidenceBundle, field: str, value: str, uom: str, url: str, quote: str, confidence: float) -> None:
    if not value:
        return
    bundle.set(
        Evidence(
            field=field,
            value=value,
            uom=uom,
            source_url=url,
            quote=quote[:180],
            extractor="html_regex",
            confidence=confidence,
        )
    )


_REGEX_HTML_CAP = 400_000


def extract_from_html(html: str, url: str) -> EvidenceBundle:
    bundle = EvidenceBundle(mfr_url=url)
    working = html or ""
    if len(working) > _REGEX_HTML_CAP:
        working = working[:320_000] + working[-80_000:]
    text = _clean_text(working)

    extra_patterns: list[tuple[str, str, str, float]] = [
        (
            "Minimum Height",
            r"Minimum Height[^\d]*(\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*Upper Rack,\s*\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*Lower Rack|\d{1,2}-?\d{0,2}/\d{0,2})",
            "in",
            0.75,
        ),
        (
            "Maximum Height",
            r"Maximum Height[^\d]*(\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*Upper Rack,\s*\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*Lower Rack)",
            "",
            0.75,
        ),
        (
            "Additional Information",
            r"(Folding Tines, Leak Detection System, Moisture Repellent Silverware Basket[^\.]{0,200})",
            "",
            0.7,
        ),
    ]

    for field, pattern, uom, confidence in _load_patterns() + extra_patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = match.group(1).strip()
        if field == "Number of Wash Cycles" and not value.isdigit():
            cycle_match = re.search(r"(\d+)\s*Wash Cycles", text, re.I)
            value = cycle_match.group(1) if cycle_match else ""
        if field == "Mounting Type":
            if value.lower().replace("-", " ") == "built in":
                value = "Built-in"
            elif value.lower() == "leg":
                value = "Leg"
        _set(bundle, field, value, uom, url, match.group(0), confidence)

    cleanboost = re.search(r"(CleanBoost™?)", text, re.I)
    if cleanboost:
        _set(bundle, "With", f"With {cleanboost.group(1)}", "", url, cleanboost.group(0), 0.8)

    third_rack = re.search(r"(Washing 3rd Rack|3rd rack with extra wash action)", text, re.I)
    silverware = re.search(r"(Water Repellent Silverware Basket|Moisture Repellent Silverware Basket)", text, re.I)
    if third_rack and silverware:
        bundle.set(
            Evidence(
                field="With",
                value=f"With {third_rack.group(1)}, {silverware.group(1)}",
                source_url=url,
                quote=f"{third_rack.group(0)} {silverware.group(0)}",
                extractor="html_regex",
                confidence=0.8,
            )
        )

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
    elif not bundle.warranty:
        loose_warranty = re.search(
            r"Warranty\s*[:\-]\s*((?:\d+\s*[- ]?Year|Limited Lifetime)[^\n.]{0,40})",
            text,
            re.I,
        )
        if loose_warranty:
            candidate = loose_warranty.group(1).strip()
            if not re.search(r"register|portal|login|click here", candidate, re.I):
                bundle.warranty = candidate

    energy_match = re.search(
        r"(\d+\s*kW-hr Annual Energy,\s*\d+\s*to\s*\d+\s*hr Delay Start Hours)",
        text,
        re.I,
    )
    if energy_match:
        _set(bundle, "Additional Information", energy_match.group(1), "", url, energy_match.group(0), 0.75)

    marketing_src = html[:80_000] if html and len(html) > 80_000 else html
    bundle.marketing = discover_marketing_text(marketing_src)
    bundle.features = discover_feature_lines(working)
    for item in extract_labeled_specs(html, url).items:
        bundle.set(item)
    return bundle


def fetch_evidence(mpn: str, domains: list[str]) -> EvidenceBundle:
    """Backward-compatible entry point; delegates to dynamic domain fetch."""
    from sources.live_enrich import fetch_manufacturer_evidence

    return fetch_manufacturer_evidence(mpn, domains)
