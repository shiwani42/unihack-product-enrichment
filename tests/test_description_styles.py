"""Description styles are identity/data, not per-SKU Python branches."""

from classify.category_router import load_template
from compose.descriptions import build_descriptions
from compose.style_table import (
    clear_style_cache,
    manufacturer_contains_brand,
    mobile_lead,
    resolve_style,
)
from extract.evidence import Evidence, EvidenceBundle


def _dishwasher_template():
    return load_template("built_in_dishwasher")


def _bundle(**fields) -> EvidenceBundle:
    bundle = EvidenceBundle()
    for field, value in fields.items():
        bundle.set(Evidence(field=field, value=value, extractor="test", confidence=0.8, quote=f"page says {value}"))
    return bundle


def test_auto_lead_uses_brand_when_manufacturer_contains_it():
    style = resolve_style()
    assert mobile_lead(style, "Whirlpool Corporation", "Whirlpool®") == "Whirlpool"
    assert mobile_lead(style, "Bosch Thermotechnology", "Bosch") == "Bosch"


def test_auto_lead_keeps_manufacturer_when_brand_is_separate():
    style = resolve_style()
    assert mobile_lead(style, "Rheem Manufacturing", "FRIGIDAIRE®") == "Rheem Manufacturing FRIGIDAIRE"
    assert mobile_lead(style, "BSH Home Appliances", "Miele") == "BSH Home Appliances Miele"


def test_whirlpool_uppercase_brand_still_matches():
    style = resolve_style()
    lead = mobile_lead(style, "Whirlpool Corporation", "WHIRLPOOL")
    assert lead == "WHIRLPOOL"
    assert "Corporation" not in lead


def test_cluster_override_is_config_not_python(tmp_path, monkeypatch):
    import json

    import compose.style_table as style_table

    (tmp_path / "description_styles.json").write_text(json.dumps({
        "default": {"mobile_lead": "auto", "mobile_fill": ["mounting"]},
        "clusters": {"Miele": {"mobile_lead": "{brand_plain}"}},
    }))
    monkeypatch.setattr(style_table, "STYLES_PATH", tmp_path / "description_styles.json")
    clear_style_cache()
    try:
        style = resolve_style(brand_key="Miele")
        assert mobile_lead(style, "BSH Home Appliances", "Miele") == "Miele"
        default = resolve_style(brand_key="Bosch")
        assert default.get("mobile_lead") == "auto"
    finally:
        clear_style_cache()


def test_third_brand_composes_without_sku_keys():
    template = _dishwasher_template()
    bundle = _bundle(Series="800 Series", **{"Mounting Type": "Built-in"})
    row = {
        "BRAND_NAME": "Bosch®",
        "MANUFACTURER_NAME": "BSH Home Appliances",
        "Product Name": "Dishwasher",
    }
    build_descriptions(row, template, bundle, "SHPM78Z55N")
    assert row["MOBILE_DESC"].startswith("BSH Home Appliances Bosch")
    assert "SHPM78Z55N" in row["MOBILE_DESC"]
    assert "Built-in Mounting" in row["SHORT_DESC"]


def test_list_with_stays_out_of_titles():
    template = _dishwasher_template()
    bundle = _bundle(Series="Eco Series", With="With Washing 3rd Rack, Water Repellent Silverware Basket")
    row = {
        "BRAND_NAME": "Bosch®",
        "MANUFACTURER_NAME": "BSH Home Appliances",
        "Product Name": "Dishwasher",
    }
    build_descriptions(row, template, bundle, "SHPM78Z55N")
    assert "3rd Rack" not in row["SHORT_DESC"]
    assert "3rd Rack" not in row["LONG_DESC1"]
    assert row["With"].startswith("With Washing 3rd Rack")


def test_with_phrase_promotes_for_any_brand_not_one_trademark():
    template = _dishwasher_template()
    bundle = _bundle(Series="Profile", With="With AutoSense")
    row = {
        "BRAND_NAME": "GE®",
        "MANUFACTURER_NAME": "GE Appliances",
        "Product Name": "Dishwasher",
    }
    build_descriptions(row, template, bundle, "PDT775SYNFS")
    assert "With AutoSense" in row["SHORT_DESC"]
    assert "With AutoSense" in row["LONG_DESC1"]


def test_style_table_has_no_sku_keys():
    import json
    from pathlib import Path

    payload = json.loads((Path(__file__).resolve().parents[1] / "compose" / "description_styles.json").read_text())
    blob = json.dumps(payload)
    assert "PDSH4816AF" not in blob
    assert "WDTS7024RZ" not in blob


def test_manufacturer_contains_brand_is_word_boundary():
    assert manufacturer_contains_brand("GE Appliances", "GE")
    assert not manufacturer_contains_brand("Rheem Manufacturing", "FRIGIDAIRE")
