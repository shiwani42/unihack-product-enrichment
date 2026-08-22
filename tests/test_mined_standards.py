"""Mined sample standards activate the same lookups official files would."""

import json
from pathlib import Path

from identity.brand_resolver import resolve_identity
from normalize.units import _fraction_table, decimal_to_fraction, split_value_uom
from scripts import mine_sample_standards
from validate.rules import validate_row


def test_miner_writes_lookups_without_inventing_official_files(tmp_path, monkeypatch):
    monkeypatch.setattr(mine_sample_standards, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mine_sample_standards, "REF_DIR", tmp_path / "empty_refs")
    mine_sample_standards.main()

    lov = json.loads((tmp_path / "lov_values.json").read_text())
    assert lov["origin"] == "mined_sample"
    assert "Leg" in lov["values_by_label"]["Mounting Type"]
    assert "Built-in" in lov["values_by_label"]["Mounting Type"]
    assert "Voltage Rating" not in lov["values_by_label"]

    uom = json.loads((tmp_path / "uom_standards.json").read_text())
    assert uom["abbreviations"]["volt"] == "V"
    assert "in" in uom["abbreviations"].values() or uom["abbreviations"].get("inch") == "in"

    brands = json.loads((tmp_path / "manufacturers.json").read_text())
    names = {(e.get("manufacturer_name"), e.get("brand_name")) for e in brands["entries"]}
    assert ("Rheem Manufacturing", "FRIGIDAIRE®") in names
    assert ("Whirlpool Corporation", "Whirlpool®") in names

    fractions = json.loads((tmp_path / "fraction_inch.json").read_text())
    mapping = fractions["decimal_to_fraction"]
    assert mapping["0.25"] == "1/4"
    assert mapping["0.5"] == "1/2"
    assert "50-1/4" in mapping.values()

    taxonomy = json.loads((tmp_path / "sample_taxonomy.json").read_text())
    assert taxonomy["template_count"] >= 8
    assert any("Dishwasher" in path or "dishwasher" in path.lower() for path in taxonomy["gold_classpaths"])


def test_miner_does_not_overwrite_official_workbook(tmp_path, monkeypatch):
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "Unicat_Lov_v1_0_Updated_With_Remarks.xlsx").write_bytes(b"fake")
    out = tmp_path / "out"
    out.mkdir()
    official = {
        "source_file": "Unicat_Lov_v1_0_Updated_With_Remarks.xlsx",
        "values_by_label": {"Mounting Type": ["Official Only"]},
    }
    (out / "lov_values.json").write_text(json.dumps(official))
    monkeypatch.setattr(mine_sample_standards, "OUT_DIR", out)
    monkeypatch.setattr(mine_sample_standards, "REF_DIR", refs)
    mine_sample_standards.main()
    payload = json.loads((out / "lov_values.json").read_text())
    assert payload["values_by_label"]["Mounting Type"] == ["Official Only"]


def test_gold_inch_decimals_become_mixed_fractions(tmp_path, monkeypatch):
    table = {
        "origin": "mined_sample",
        "decimal_to_fraction": {"0.25": "1/4", "0.5": "1/2", "50.25": "50-1/4"},
    }
    path = tmp_path / "fraction_inch.json"
    path.write_text(json.dumps(table))
    monkeypatch.setattr("normalize.units.FRACTION_TABLE", path)
    _fraction_table.cache_clear()
    assert decimal_to_fraction("0.25") == "1/4"
    assert decimal_to_fraction("50.25") == "50-1/4"
    assert split_value_uom("50.25", "in") == ("50-1/4", "in")
    assert split_value_uom("120", "V") == ("120", "V")
    _fraction_table.cache_clear()


def test_sample_brands_resolve_from_observed_fields():
    trex = resolve_identity("X1", "TREX LINEAGE GROOVED DECKING", "TREX", "", "Parksite (6151)")
    assert trex.brand_key == "Trex"
    assert "trex.com" in trex.domains

    philips = resolve_identity("65-123", "LED ceiling light", "", "", "Phillips Lighting (5831)")
    assert philips.brand_key == "Philips"

    dewalt = resolve_identity("DCB518", "DEWALT disc", "", "DEWALT", "Black & Decker/dewlt (2585)")
    assert dewalt.brand_key == "DEWALT"


def test_mined_lov_still_warns_on_unknown_mounting(tmp_path, monkeypatch):
    ref = {"values_by_label": {"Mounting Type": ["Leg", "Built-in"]}}
    path = tmp_path / "lov_values.json"
    path.write_text(json.dumps(ref))
    monkeypatch.setattr("validate.rules.REFERENCE_LOV_PATH", path)
    monkeypatch.setattr("validate.rules._reference_values_cache", None)
    row = {
        "Product Name": "Dishwasher",
        "Classpath": "A>B>C",
        "ATTRIBUTE_LABEL 1": "Mounting Type",
        "ATTRIBUTE_VALUE 1": "Ceiling Mount",
    }
    issues = validate_row(row, category_id="built_in_dishwasher")
    assert any("not in LOV" in issue.message for issue in issues)
