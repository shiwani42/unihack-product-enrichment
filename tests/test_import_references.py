"""Tests: dashboard reference-file importers activate pipeline lookups."""

import json

import pytest

openpyxl = pytest.importorskip("openpyxl")

from scripts import import_references


@pytest.fixture(autouse=True)
def _redirect_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(import_references, "OUT_DIR", tmp_path / "reference_out")
    monkeypatch.setattr(import_references, "REFERENCE200_DIR", tmp_path / "reference200_out")
    yield


def _write_xlsx(path, sheet_name, rows):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_import_lov(tmp_path):
    _write_xlsx(
        tmp_path / "Unicat_Lov_v1_0_Updated_With_Remarks.xlsx",
        "LOV",
        [
            ["junk", "notes"],
            ["Classpath", "Attribute Label", "Attribute Values"],
            ["A>B>C", "Mounting Type", "Leg"],
            ["A>B>C", "Mounting Type", "Built-in"],
            ["D>E>F", "Color", "Black"],
        ],
    )
    out = import_references.import_lov(tmp_path)
    payload = json.loads(out.read_text())
    assert payload["values_by_label"]["Mounting Type"] == ["Leg", "Built-in"]
    assert payload["labels"] == 2


def test_import_manufacturers_exact_casing(tmp_path):
    _write_xlsx(
        tmp_path / "UniCat_Manufacturer_and_Brand_List.xlsx",
        "List",
        [
            ["MANUFACTURER_NAME", "MANUFACTURER_CODE", "BRAND_NAME", "BRAND_CODE"],
            ["Whirlpool Corporation", "123", "Whirlpool®", "WPL"],
            ["Frigidaire Company", "456", "FRIGIDAIRE®", "FRG"],
            ["Whirlpool Corporation", "123", "Whirlpool®", "WPL"],
        ],
    )
    out = import_references.import_manufacturers(tmp_path)
    payload = json.loads(out.read_text())
    assert payload["count"] == 2
    names = {e["manufacturer_name"] for e in payload["entries"]}
    assert "Whirlpool Corporation" in names


def test_import_fractions_side_by_side_blocks(tmp_path):
    _write_xlsx(
        tmp_path / "Decimal_Fraction.xlsx",
        "Sheet1",
        [
            ["Fraction", "Decimal", "Fraction", "Decimal"],
            ["1/2", 0.5, "1-3/4", 1.75],
        ],
    )
    out = import_references.import_fractions(tmp_path)
    mapping = json.loads(out.read_text())["decimal_to_fraction"]
    assert mapping["0.5"] == "1/2"
    assert mapping["1.75"] == "1-3/4"


def test_import_reference200_sheets(tmp_path):
    path = tmp_path / "Unilog-Sample_200_Items-Input-vs-Output.xlsx"
    workbook = openpyxl.Workbook()
    input_sheet = workbook.active
    input_sheet.title = "Input"
    input_sheet.append(["Mfg_Part_Num", "Part_Desc"])
    input_sheet.append(["MPN-1", "desc one"])
    delivery_sheet = workbook.create_sheet("Delivery Format")
    delivery_sheet.append(["Mfg_Part_Num", "BRAND_NAME"])
    delivery_sheet.append(["MPN-1", "ACME®"])
    workbook.save(path)

    out_dir = import_references.import_reference200(tmp_path)
    assert (out_dir / "input.csv").exists()
    assert (out_dir / "expected.csv").read_text().splitlines()[1].startswith("MPN-1")


def test_missing_reference_dir_is_noop(tmp_path):
    from scripts.import_references import main as import_main
    import sys

    sys.argv = ["import_references.py", "--src", str(tmp_path / "empty")]
    import_main()
    assert True


def test_header_columns_identify_renamed_workbooks(tmp_path):
    _write_xlsx(
        tmp_path / "dashboard_export.xlsx",
        "Sheet1",
        [
            ["Classpath", "Attribute Label", "Attribute Values"],
            ["A>B>C", "Finish", "Chrome"],
        ],
    )
    _write_xlsx(
        tmp_path / "brands_from_judge.xlsx",
        "List",
        [
            ["MANUFACTURER_NAME", "BRAND_NAME"],
            ["Whirlpool Corporation", "Whirlpool®"],
        ],
    )
    assert import_references.classify_workbook(tmp_path / "dashboard_export.xlsx") == "lov"
    assert import_references.classify_workbook(tmp_path / "brands_from_judge.xlsx") == "manufacturers"
    lov = json.loads(import_references.import_lov(tmp_path).read_text())
    assert lov["values_by_label"]["Finish"] == ["Chrome"]
    brands = json.loads(import_references.import_manufacturers(tmp_path).read_text())
    assert brands["entries"][0]["brand_name"] == "Whirlpool®"


def test_fuzzy_lov_filename_still_imports(tmp_path):
    _write_xlsx(
        tmp_path / "Unicat_Lov_updated_with_remarks.xlsx",
        "LOV",
        [
            ["Classpath", "Attribute Label", "Attribute Values"],
            ["A>B>C", "Mounting Type", "Leg"],
        ],
    )
    out = import_references.import_lov(tmp_path)
    payload = json.loads(out.read_text())
    assert payload["values_by_label"]["Mounting Type"] == ["Leg"]


def test_extra_faucets_lov_merges_into_values(tmp_path):
    _write_xlsx(
        tmp_path / "Unicat_Lov_v1_0_Updated_With_Remarks.xlsx",
        "LOV",
        [
            ["Classpath", "Attribute Label", "Attribute Values"],
            ["A>B>C", "Finish", "Chrome"],
        ],
    )
    _write_xlsx(
        tmp_path / "FAUCETS_LOV.xlsx",
        "LOV",
        [
            ["Attribute Label", "Attribute Values"],
            ["Finish", "Brushed Nickel"],
            ["Handle Type", "Lever"],
        ],
    )
    out = import_references.import_lov(tmp_path)
    payload = json.loads(out.read_text())
    assert "Chrome" in payload["values_by_label"]["Finish"]
    assert "Brushed Nickel" in payload["values_by_label"]["Finish"]
    assert payload["values_by_label"]["Handle Type"] == ["Lever"]


def test_ensure_imports_workbook_a_judge_dropped(tmp_path, monkeypatch):
    refs = tmp_path / "refs"
    refs.mkdir()
    _write_xlsx(
        refs / "Decimal_Fraction.xlsx",
        "Sheet1",
        [["Fraction", "Decimal"], ["1/2", 0.5]],
    )
    monkeypatch.setattr(import_references, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(import_references, "reference_search_dirs", lambda: [refs])
    import identity.brand_resolver as brand_resolver
    import normalize.units as units
    import validate.rules as rules

    previous = (
        rules.REFERENCE_LOV_PATH,
        brand_resolver.REFERENCE_MANUFACTURERS_PATH,
        units.FRACTION_TABLE,
    )
    import_references.reset_ensure_for_tests()
    try:
        found = import_references.ensure_official_references()
        assert found.get("fractions")
        mapping = json.loads((tmp_path / "out" / "fraction_inch.json").read_text())["decimal_to_fraction"]
        assert mapping["0.5"] == "1/2"
    finally:
        rules.REFERENCE_LOV_PATH, brand_resolver.REFERENCE_MANUFACTURERS_PATH, units.FRACTION_TABLE = previous
        rules._reference_values_cache = None
        brand_resolver._reference_index_cache = None
        units._fraction_table.cache_clear()
        import_references.reset_ensure_for_tests()
