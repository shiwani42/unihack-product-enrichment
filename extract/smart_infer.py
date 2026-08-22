"""Rule-based smart inference when LLM is unavailable."""

import re

from extract.evidence import Evidence, EvidenceBundle
from ingest.industrial_parser import parse_industrial_desc


def infer_smart_attributes(part_desc: str, mpn: str, category_id: str) -> EvidenceBundle:
    bundle = parse_industrial_desc(part_desc)
    lower = part_desc.lower()

    if category_id == "generic_industrial" and len(bundle.items) < 2:
        tokens = re.findall(r"[A-Za-z0-9/\"\.]+", part_desc)
        if tokens:
            bundle.set(
                Evidence(
                    field="Product Type",
                    value=" ".join(tokens[:4]),
                    source_url="input:Part_Desc",
                    quote=part_desc[:120],
                    extractor="smart_infer",
                    confidence=0.45,
                )
            )

    if re.search(r"grind(?:ing)? wheel|cut and grind|dual metal", lower):
        bundle.set(
            Evidence(
                field="Product Type",
                value="Grinding Wheel",
                source_url="input:Part_Desc",
                quote=part_desc[:120],
                extractor="smart_infer",
                confidence=0.7,
            )
        )
        bundle.set(
            Evidence(
                field="Application",
                value="Metal Grinding",
                source_url="input:Part_Desc",
                quote=part_desc[:120],
                extractor="smart_infer",
                confidence=0.65,
            )
        )

    return bundle
