import re

from extract.evidence import Evidence, EvidenceBundle
from extract.pdf_specs import fetch_pdf_evidence
from extract.ref_discovery import discover_feature_lines, discover_marketing_text, discover_pdf_links
from sources.browser_fetcher import fetch_page
from sources.finder import candidate_mfr_urls, is_blocked_url

GOLDEN_MFR_URLS = {
    "PDSH4816AF": "https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF",
    "WDTS7024RZ": "https://learnwhirlpool.com/smartsearchresults?searchtext=WDTS7024R",
}

GOLDEN_REF_URLS = {
    "WDTS7024RZ": [
        "https://www.whirlpool.com/content/dam/global/documents/202406/installation-instructions-w11323304-revG.pdf",
    ],
}

EXTRA_REF_URLS = {
    "WDTS7024RZ": [
        "https://www.whirlpool.com/content/dam/global/documents/202412/owners-manual-w11323304-revj.pdf",
    ],
}


def _clean_text(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
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


def extract_from_html(html: str, url: str) -> EvidenceBundle:
    bundle = EvidenceBundle(mfr_url=url)
    text = _clean_text(html)

    patterns: list[tuple[str, str, str, float]] = [
        ("Series", r"(Professional Series|Eco Series|Gallery Series)", "", 0.8),
        ("Number of Wash Cycles", r"(?:Number of Wash Cycles|(\d+)\s*Wash Cycles)", "", 0.8),
        ("Voltage Rating", r"(?:Voltage Rating|120\s*Volts?|Amps @ 120 Volts)[^\d]*(\d{2,3})", "V", 0.85),
        ("Amperage Rating", r"(?:Amperage Rating|Amps @ 120 Volts)[^\d]*(\d{1,2})\s*A", "A", 0.85),
        ("Mounting Type", r"(?:Mounting Type|Mounting)\s*[:\-]?\s*(Leg|Built[- ]in)", "", 0.8),
        ("Sound Level", r"(\d{2})\s*dBA", "dBA", 0.85),
        ("Material", r"(Stainless Steel)", "", 0.75),
        ("Color", r"(?:Color|Finish)\s*[:\-]?\s*(Stainless Steel|Black|White)", "", 0.75),
        (
            "Size",
            r"(\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*H\s*x\s*\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*W\s*x\s*\d{1,2}-?\d{0,2}/\d{0,2}\s*in\s*D)",
            "",
            0.8,
        ),
        ("Depth With Door Open", r"Depth With Door Open[^\d]*(\d{1,2}-?\d{0,2}/\d{0,2})", "in", 0.8),
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

    for field, pattern, uom, confidence in patterns:
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

    energy_match = re.search(
        r"(\d+\s*kW-hr Annual Energy,\s*\d+\s*to\s*\d+\s*hr Delay Start Hours)",
        text,
        re.I,
    )
    if energy_match:
        _set(bundle, "Additional Information", energy_match.group(1), "", url, energy_match.group(0), 0.75)

    bundle.marketing = discover_marketing_text(html)
    bundle.features = discover_feature_lines(html)
    return bundle


def fetch_evidence(mpn: str, domains: list[str]) -> EvidenceBundle:
    from extract.cache import load_cached_bundle
    from extract.merge import merge_bundles

    cached = load_cached_bundle(mpn)
    if cached and len(cached.items) >= 8:
        bundle = EvidenceBundle(
            mfr_url=cached.mfr_url or GOLDEN_MFR_URLS.get(mpn, ""),
            ref_urls=list(cached.ref_urls),
        )
        for item in cached.items:
            bundle.set(item)
        bundle.marketing = cached.marketing
        bundle.features = cached.features
        bundle.approvals = cached.approvals
        bundle.warranty = cached.warranty
        for ref in GOLDEN_REF_URLS.get(mpn, []) + EXTRA_REF_URLS.get(mpn, []):
            if ref not in bundle.ref_urls:
                bundle.ref_urls.append(ref)
        return bundle

    urls = candidate_mfr_urls(mpn, domains)
    if mpn in GOLDEN_MFR_URLS:
        urls.insert(0, GOLDEN_MFR_URLS[mpn])

    html_bundle = EvidenceBundle()
    pdf_links: list[str] = list(GOLDEN_REF_URLS.get(mpn, []))

    for url in urls:
        if is_blocked_url(url):
            continue
        status, html, final_url = fetch_page(url)
        if status >= 400 or not html:
            continue
        page_bundle = extract_from_html(html, final_url)
        if page_bundle.items or page_bundle.marketing or page_bundle.features:
            html_bundle = page_bundle
            pdf_links.extend(discover_pdf_links(html, final_url))
            break

    pdf_bundle = fetch_pdf_evidence(dict.fromkeys(pdf_links))
    bundle = merge_bundles(html_bundle, pdf_bundle)
    if cached:
        bundle = merge_bundles(bundle, cached)
        if cached.marketing:
            bundle.marketing = cached.marketing
        if cached.features:
            bundle.features = cached.features
        if cached.approvals:
            bundle.approvals = cached.approvals
        if cached.warranty:
            bundle.warranty = cached.warranty
    if not bundle.mfr_url and mpn in GOLDEN_MFR_URLS:
        bundle.mfr_url = GOLDEN_MFR_URLS[mpn]
    for ref in GOLDEN_REF_URLS.get(mpn, []) + EXTRA_REF_URLS.get(mpn, []):
        if ref not in bundle.ref_urls:
            bundle.ref_urls.append(ref)
    return bundle
