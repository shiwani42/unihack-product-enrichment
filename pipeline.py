from dataclasses import dataclass

from classify.category_router import route_category
from compose.assets import apply_asset_fields
from compose.descriptions import build_descriptions
from extract.cache import load_cached_bundle, save_cached_bundle
from extract.desc_parser import build_abrasive_descriptions, extract_from_part_desc
from extract.html_specs import fetch_evidence
from extract.merge import merge_bundles
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


def _hydrate_bundle(mpn: str, live_bundle) -> object:
    cached = load_cached_bundle(mpn)
    if cached and len(live_bundle.items) < 5:
        merged = merge_bundles(live_bundle, cached)
        if cached.marketing and not merged.marketing:
            merged.marketing = cached.marketing
        if cached.features and not merged.features:
            merged.features = cached.features
        if cached.approvals and not merged.approvals:
            merged.approvals = cached.approvals
        if cached.warranty and not merged.warranty:
            merged.warranty = cached.warranty
        return merged
    if len(live_bundle.items) >= 5:
        save_cached_bundle(mpn, live_bundle)
    return live_bundle


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
    bundle = None
    if template:
        apply_taxonomy(output, template)
        if template.category_id == "built_in_dishwasher":
            live_bundle = fetch_evidence(mpn, identity.domains)
            bundle = _hydrate_bundle(mpn, live_bundle)
            output["MFR URL"] = bundle.mfr_url
            for index, ref_url in enumerate(bundle.ref_urls[:5], start=1):
                output[f"Ref URL {index}"] = ref_url
            apply_template_attributes(output, template, bundle)
            build_descriptions(output, template, bundle, mpn)
            if bundle.approvals:
                output["Standard/Approvals"] = bundle.approvals
            if bundle.warranty:
                output["Warranty"] = bundle.warranty
            apply_asset_fields(output, mpn)
        elif template.category_id == "metal_cutoff_disc":
            bundle = extract_from_part_desc(part_desc, mpn)
            apply_template_attributes(output, template, bundle)
            build_abrasive_descriptions(output, template, bundle, mpn)

    evidence_count = len(bundle.items) if bundle else 0
    confidence_band = overall_confidence(output, identity.confidence, evidence_count)
    issues = validate_row(output)
    return EnrichmentResult(
        row=output,
        confidence_band=confidence_band,
        evidence_count=evidence_count,
        issues=issues,
    )
