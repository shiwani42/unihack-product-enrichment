"""Guards so unseen SKUs do not repeat the batch voltage / CCT / empty / PDF issues."""

from classify.category_router import load_template, route_category
from compose.marketing import apply_marketing_fields
from extract.desc_parser import extract_from_part_desc
from extract.evidence import Evidence, EvidenceBundle
from extract.generic_parser import extract_generic_from_desc
from extract.html_specs import extract_from_html
from ingest.csv_io import is_readable_text, sanitize_cell
from normalize.mapper import apply_template_attributes
from normalize.units import split_value_uom
from normalize.values import cleanse_attribute, cleanse_output_row, normalize_color_temperature
from validate.rules import validate_row


def test_wattage_is_not_relabeled_as_volts():
    assert split_value_uom("60 W", expected_uom="V") == ("60", "W")
    assert split_value_uom("5 W", expected_uom="V") == ("5", "W")
    value, uom = cleanse_attribute("Voltage Rating", "5", "W", "generic_industrial")
    assert value == "" and uom == ""
    value, uom = cleanse_attribute("Voltage Rating", "60 W", "V", "generic_industrial")
    assert value == "" and uom == ""
    value, uom = cleanse_attribute("Wattage", "60 W", "", "generic_industrial")
    assert value == "60" and uom == "W"


def test_voltage_slot_does_not_take_wattage_evidence():
    template = load_template("generic_industrial")
    bundle = EvidenceBundle()
    bundle.set(Evidence(field="Wattage", value="339", uom="W", source_url="https://oem.example/p", extractor="html", confidence=0.8))
    bundle.set(Evidence(field="Voltage Rating", value="5", uom="W", source_url="https://oem.example/p", extractor="html", confidence=0.7))
    row: dict[str, str] = {"Mfg_Part_Num": "DC5004WE"}
    apply_template_attributes(row, template, bundle)
    labels = [row.get(f"ATTRIBUTE_LABEL {i}", "") for i in range(1, 51)]
    voltage_slot = labels.index("Voltage Rating") + 1
    assert row.get(f"ATTRIBUTE_VALUE {voltage_slot}", "") == ""
    wattage_slots = [i + 1 for i, label in enumerate(labels) if label == "Wattage"]
    assert wattage_slots
    assert row[f"ATTRIBUTE_VALUE {wattage_slots[0]}"] == "339"
    assert row[f"ATTRIBUTE_UOM {wattage_slots[0]}"] == "W"


def test_w_slash_is_not_harvested_as_wattage():
    template = load_template("generic_industrial")
    bundle = extract_generic_from_desc("Timer 2 w/Half Hour Delay", "T-1", template)
    assert bundle.get("Wattage") is None


def test_color_temperature_not_harvested_from_mpn():
    assert normalize_color_temperature("2266K", mpn="SMC2266KS") == ""
    assert normalize_color_temperature("5333K", mpn="D25333K") == ""
    assert normalize_color_temperature("4400K", mpn="JT9-714400K") == ""
    assert normalize_color_temperature("4000K", mpn="S11828") == "4000K"
    assert normalize_color_temperature("Multi CCT", mpn="HLBSL609FS5") == "Multi CCT"

    template = load_template("led_lighting")
    bundle = extract_generic_from_desc("SMC2266KS LED Ceiling Light", "SMC2266KS", template)
    assert bundle.get("Color Temperature") is None
    bundle = extract_generic_from_desc("6in LED Downlight 4000K", "HLB-1", template)
    assert bundle.get("Color Temperature").value == "4000K"


def test_cleansed_cct_does_not_fail_lov():
    row = {
        "MANUFACTURER_PART_NUMBER": "SMC2266KS",
        "ATTRIBUTE_LABEL 1": "Color Temperature",
        "ATTRIBUTE_VALUE 1": "2266K",
        "ATTRIBUTE_UOM 1": "",
        "ATTRIBUTE_LABEL 2": "Product Type",
        "ATTRIBUTE_VALUE 2": "LED Ceiling Light",
        "MOBILE_DESC": "x" * 65,
    }
    cleanse_output_row(row, "led_lighting")
    assert row["ATTRIBUTE_VALUE 1"] == ""
    issues = validate_row(row, category_id="led_lighting")
    assert not any("Color Temperature" in issue.message for issue in issues)


def test_sanding_sponge_gets_grit_and_product_type():
    bundle = extract_from_part_desc("Diablo 220 Grit - Flat Edge Sanding Sponge", "DFBLBLOMFN01G")
    assert bundle.get("Grit").value == "220"
    assert bundle.get("Product Type").value == "Sanding Sponge"
    template = load_template("sanding_abrasive")
    row: dict[str, str] = {}
    apply_template_attributes(row, template, bundle)
    assert any(row.get(f"ATTRIBUTE_VALUE {i}") for i in range(1, 51))
    issues = validate_row(row, category_id="sanding_abrasive")
    assert not any("no attributes" in issue.message for issue in issues)


def test_screw_setter_is_not_an_empty_grinding_wheel():
    template = route_category("#2 Drywall Screw Setter", "Diablo")
    assert template.category_id == "power_tool_accessory"
    bundle = extract_from_part_desc("#2 Drywall Screw Setter", "DDWSSB")
    assert bundle.get("Product Type").value == "Screw Setter"
    row: dict[str, str] = {}
    apply_template_attributes(row, load_template("grinding_wheel"), EvidenceBundle())
    assert row["ATTRIBUTE_VALUE 1"] == "Grinding Wheel"


def test_pdf_bytes_never_become_marketing():
    junk = "%PDF-1.4\n1 0 obj\n<<>>\nendobj\n\x00\x04binary"
    assert not is_readable_text(junk)
    assert sanitize_cell(junk) == ""
    bundle = extract_from_html(junk, "https://oem.example/spec")
    assert bundle.marketing == ""
    assert not bundle.items
    out: dict[str, str] = {}
    apply_marketing_fields(out, EvidenceBundle(marketing=junk, features=[junk, "Quiet wash"]))
    assert out.get("MARKETING_DESCRIPTION", "") == ""
    assert out["ITEM_FEATURES_1"] == "Quiet wash"
    row = {
        "MARKETING_DESCRIPTION": junk,
        "LONG_DESC1": junk,
        "MOBILE_DESC": "x" * 65,
        "Product Name": "Washer",
        "Classpath": "A>B>C",
    }
    cleanse_output_row(row, "generic_industrial")
    assert row["MARKETING_DESCRIPTION"] == ""
    assert row["LONG_DESC1"] == ""
