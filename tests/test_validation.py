from ingest.csv_io import load_output_headers
from pipeline import enrich_input_row
from validate.rules import validate_row


def test_validate_rejects_ecommerce_source():
    row = {"MFR URL": "https://www.amazon.com/product/123", "Product Name": "Test"}
    issues = validate_row(row, category_id="generic_industrial")
    assert any("blocked ecommerce" in issue.message for issue in issues)

    row = {"Ref URL 1": "https://www.dkhardware.com/product/123", "Product Name": "Test"}
    issues = validate_row(row, category_id="generic_industrial")
    assert any("blocked ecommerce" in issue.message for issue in issues)


def test_validate_allows_distributor_ref_url():
    row = {"Ref URL 1": "https://www.grainger.com/product/X1", "Product Name": "Test"}
    issues = validate_row(row, category_id="generic_industrial")
    assert not any("blocked ecommerce" in issue.message for issue in issues)


def test_validate_mobile_length_rules():
    row = {"MOBILE_DESC": "short", "Product Name": "Test", "Classpath": "A>B>C"}
    issues = validate_row(row, category_id="generic_industrial")
    assert any(issue.field == "MOBILE_DESC" for issue in issues)


def test_enrich_never_raises_on_bad_row():
    headers = load_output_headers()
    result = enrich_input_row({"Mfg_Part_Num": "", "Part_Desc": ""}, headers)
    assert result.row is not None
    assert result.confidence_band
