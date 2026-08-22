"""Smoke tests: Solution Guide compliance checker."""

from scripts.compliance_check import (
    _char_limits,
    _placeholder_leakage,
    _source_url_coverage,
    _uom_style,
)

HEADERS = [
    "Mfg_Part_Num",
    "Part_Desc",
    "INVOICE_DESC",
    "MOBILE_DESC",
    "SHORT_DESC",
    "LONG_DESC1",
    "MFR URL",
]


def test_placeholder_leakage_detected():
    rows = [{"E1_Brand": "x", "BRAND_NAME": "-- Unbranded --"}]
    assert _placeholder_leakage(rows, ["E1_Brand", "BRAND_NAME"]) == 1


def test_uom_style_ignores_quoted_source_desc():
    row = {
        "Part_Desc": 'X1 Diablo 12"x20mm Disc',
        "LONG_DESC1": 'ACME, Disc, X1, Diablo 12"x20mm Disc',
        "SHORT_DESC": "24 in W",
        "RETAIL_DESC": "",
    }
    result = _uom_style([row])
    assert result["violations"] == 0


def test_char_limits_report():
    rows = [{"INVOICE_DESC": "A" * 41, "MOBILE_DESC": "B" * 70}]
    report = _char_limits(rows)
    assert report["INVOICE_DESC"]["over_limit"] == 1
    assert report["MOBILE_DESC"]["over_limit"] == 0


def test_source_url_coverage():
    rows = [
        {"ATTRIBUTE_VALUE 1": "v", "Product Name": "P", "MFR URL": "https://mfr.com/x", "Ref URL 1": ""},
        {"ATTRIBUTE_VALUE 1": "", "MFR URL": ""},
    ]
    coverage = _source_url_coverage(rows)
    assert coverage["populated_rows"] == 1
    assert coverage["mfr_url_pct"] == 100.0
