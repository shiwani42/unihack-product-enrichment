from dataclasses import dataclass

from classify.category_router import route_category
from compose.descriptions import build_descriptions
from extract.html_specs import fetch_evidence
from identity.brand_resolver import resolve_identity
from ingest.csv_io import empty_output_row
from normalize.mapper import apply_taxonomy, apply_template_attributes
from validate.rules import overall_confidence, validate_row


@dataclass
class EnrichmentResult:
    row: dict[str, str]
    confidence_band: str
    evidence_count: int
    issues: list


def enrich_input_row(input_row: dict[str, str], headers: list[str]) -> EnrichmentResult:
    output = empty_output_row(headers)
    mpn = input_row["Mfg_Part_Num"]
    part_desc = input_row["Part_Desc"]

    for field in (
        "Mfg_Part_Num",
        "Part_Desc",
        "E1_Brand",
        "Unilog_Brand",
        "DIB_Brand",
        "Part_Manuf",
    ):
        output[field] = input_row.get(field, "")

    output["MANUFACTURER_PART_NUMBER"] = mpn
    identity = resolve_identity(
        mpn=mpn,
        part_desc=part_desc,
        e1_brand=input_row.get("E1_Brand", ""),
        dib_brand=input_row.get("DIB_Brand", ""),
    )
    output["MANUFACTURER_NAME"] = identity.manufacturer_name
    output["BRAND_NAME"] = identity.brand_name

    template = route_category(part_desc, identity.brand_key)
    bundle = fetch_evidence(mpn, identity.domains) if template else None

    if template and bundle:
        output["MFR URL"] = bundle.mfr_url
        for index, ref_url in enumerate(bundle.ref_urls[:5], start=1):
            output[f"Ref URL {index}"] = ref_url
        apply_taxonomy(output, template)
        apply_template_attributes(output, template, bundle)
        build_descriptions(output, template, bundle, mpn)

    evidence_count = len(bundle.items) if bundle else 0
    confidence_band = overall_confidence(output, identity.confidence, evidence_count)
    issues = validate_row(output)
    return EnrichmentResult(
        row=output,
        confidence_band=confidence_band,
        evidence_count=evidence_count,
        issues=issues,
    )
