from ingest.input_analyzer import analyze_input_row, catalog_id, catalog_search_mpn, expand_abbreviations, normalize_mpn
from normalize.units import split_value_uom
from normalize.values import normalize_mounting
from pipeline import enrich_input_row
from ingest.csv_io import load_output_headers, read_input_rows
from app.config import DEFAULT_INPUT


def test_normalize_mpn_strips_suffix():
    assert normalize_mpn("54151-JR-UPC") == "54151-JR"


def test_distributor_prefix_becomes_manufacturer_catalog_id():
    assert catalog_id("3MABR-7100075678", "3M") == "7100075678"
    assert catalog_id("49-94-0013", "Milwaukee") == "49-94-0013"
    assert catalog_search_mpn("3MABR-7100075678", "3M") == "7100075678"
    assert catalog_search_mpn("WDTS7024RZ", "Whirlpool") == "WDTS7024R"
    assert catalog_search_mpn("DCB518ASTS06G", "Diablo") == "DCB518ASTS06G"


def test_expand_cryptic_description():
    expanded, found = expand_abbreviations(
        "3/8 CPLG BRS 150#",
        {"CPLG": "Coupling", "BRS": "Brass", "150#": "150 Pound"},
    )
    assert "Coupling" in expanded
    assert "Brass" in expanded
    assert "CPLG" in found


def test_split_voltage_value_uom():
    value, uom = split_value_uom("120 V")
    assert value == "120"
    assert uom == "V"


def test_mounting_normalization():
    assert normalize_mounting("built in") == "Built-in"


def test_analyze_input_detects_empty_brand_columns():
    analyzed = analyze_input_row(
        {
            "Mfg_Part_Num": "DBD090094101F",
            "Part_Desc": 'DBD090094101F Diablo 9" Metal Cut-Off Disc',
            "E1_Brand": "-- Unbranded --",
            "Unilog_Brand": "-- No Unilog Brand --",
            "DIB_Brand": "-- No DIB Brand --",
            "Part_Manuf": "Freud Inc (2435)",
        }
    )
    assert analyzed.normalized_mpn == "DBD090094101F"
    assert "Diablo" in analyzed.expanded_desc


def test_enrich_populates_canonical_key():
    headers = load_output_headers()
    row = next(r for r in read_input_rows(DEFAULT_INPUT) if r["Mfg_Part_Num"] == "DBD090094101F")
    result = enrich_input_row(row, headers)
    assert result.canonical_key
    assert "Diablo" in result.canonical_key or result.row.get("BRAND_NAME")
