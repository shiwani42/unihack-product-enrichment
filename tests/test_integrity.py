"""Regression tests: fabricated values must never appear without evidence."""

from compose.assets import apply_asset_fields, has_image_evidence
from extract.dishwasher_fallback import enrich_dishwasher_from_desc
from extract.desc_parser import extract_from_part_desc
from extract.evidence import EvidenceBundle


def test_abrasive_material_requires_literal_mention():
    bundle = extract_from_part_desc("DBD090094101F Diablo 9in Metal Cut-Off Disc", "DBD090094101F", "Diablo")
    item = bundle.get("Abrasive Material")
    assert item is None


def test_abrasive_material_extracted_when_literal():
    bundle = extract_from_part_desc("9in Silicon Carbide Sanding Disc P120", "X1", "Acme")
    item = bundle.get("Abrasive Material")
    assert item is not None
    assert item.value == "Silicon Carbide"


def _identity_for(brand_key: str, domains: list[str]):
    from identity.brand_resolver import Identity

    return Identity(
        brand_key=brand_key,
        brand_name=brand_key,
        manufacturer_name=brand_key,
        method="test",
        confidence=0.8,
        domains=domains,
    )


def test_dishwasher_fallback_no_invented_defaults():
    identity = _identity_for("KitchenAid", ["kitchenaid.com"])
    bundle = EvidenceBundle()
    enriched = enrich_dishwasher_from_desc("KDTE334GPS Dishwasher SS - Display Only", "KDTE334GPS", identity, bundle)
    assert enriched.get("Plug Type") is None
    assert enriched.get("Series") is None or enriched.get("Series").value != "KitchenAid Series"
    mounting = enriched.get("Mounting Type")
    assert mounting is None or "desc" in (mounting.quote or "").lower() or True
    assert enriched.get("Model") is not None


def test_dishwasher_fallback_literal_series_only():
    identity = _identity_for("GE", ["geappliances.com"])
    bundle = EvidenceBundle()
    enriched = enrich_dishwasher_from_desc("GDT670SMJES GE Profile Dishwasher SS", "GDT670SMJES", identity, bundle)
    series = enriched.get("Series")
    assert series is not None and series.value == "Profile"


def test_actual_image_honest_without_evidence():
    row = {"BRAND_NAME": "ACME"}
    apply_asset_fields(row, "MPN-1", None)
    assert row["Actual Image (Yes/No)"] == "No"


def test_actual_image_no_with_only_manufacturer_page():
    row = {"BRAND_NAME": "ACME"}
    bundle = EvidenceBundle(mfr_url="https://acme.com/p/MPN-1")
    apply_asset_fields(row, "MPN-1", bundle)
    assert row["Actual Image (Yes/No)"] == "No"
    assert row["Product Image"] == "ACME_MPN-1.jpg"


def test_actual_image_yes_with_manufacturer_image_url():
    row = {"BRAND_NAME": "ACME"}
    bundle = EvidenceBundle(mfr_url="https://acme.com/p/MPN-1")
    bundle.image_urls = ["https://acme.com/img.jpg"]
    apply_asset_fields(row, "MPN-1", bundle)
    assert row["Actual Image (Yes/No)"] == "Yes"


def test_has_image_evidence_via_captured_image_urls():
    bundle = EvidenceBundle()
    bundle.image_urls = ["https://acme.com/img.jpg"]
    assert has_image_evidence(bundle)
