import re

from classify.category_router import CategoryTemplate
from extract.evidence import Evidence, EvidenceBundle
from identity.brand_resolver import Identity
from sources.finder import candidate_mfr_urls


def enrich_dishwasher_from_desc(
    part_desc: str,
    mpn: str,
    identity: Identity,
    bundle: EvidenceBundle,
) -> EvidenceBundle:
    """Fill dishwasher attributes from Part_Desc when manufacturer fetch is thin."""
    text = part_desc
    source = "input:Part_Desc"

    def add(field: str, value: str, confidence: float = 0.55) -> None:
        if not value or bundle.get(field):
            return
        bundle.set(
            Evidence(
                field=field,
                value=value,
                source_url=source,
                quote=text[:120],
                extractor="dishwasher_desc_fallback",
                confidence=confidence,
            )
        )

    add("Model", mpn, 0.9)
    if re.search(r"\bSS\b|Stainless", text, re.I):
        add("Material", "Stainless Steel", 0.7)
        add("Color", "Stainless Steel", 0.65)
    if re.search(r"\bBlack\b", text, re.I):
        add("Color", "Black", 0.65)
    if re.search(r"Built.?in|BLTLN", text, re.I):
        add("Mounting Type", "Built-in", 0.6)
    elif re.search(r"\bLeg\b", text, re.I):
        add("Mounting Type", "Leg", 0.6)
    series = re.search(r"\b(Profile|Ultra|Pro|Max|Elite|Premium)\b", text, re.I)
    if series:
        add("Series", series.group(1).title(), 0.55)

    if identity.domains and not bundle.mfr_url:
        candidates = candidate_mfr_urls(mpn, identity.domains)
        if candidates:
            bundle.mfr_url = candidates[0]

    return bundle
