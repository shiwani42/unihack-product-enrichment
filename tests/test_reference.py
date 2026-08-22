from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS, REFERENCE_MPNS
from ingest.csv_io import load_output_headers, read_input_rows
from pipeline import enrich_input_row
from validate.reference_test import compare_rows


def test_reference_rows_enrich_without_seed_cache():
    """Hermetic runs do not read precooked SKU caches. Score vs golden
    delivery format is a live-manufacturer target, not an offline guarantee."""
    headers = load_output_headers()
    reference_rows = read_input_rows(DEFAULT_OUTPUT_HEADERS)
    reference_by_mpn = {row["Mfg_Part_Num"]: row for row in reference_rows}
    input_rows = read_input_rows(DEFAULT_INPUT)
    input_by_mpn = {row["Mfg_Part_Num"]: row for row in input_rows}

    for mpn in REFERENCE_MPNS:
        expected = reference_by_mpn[mpn]
        result = enrich_input_row(input_by_mpn[mpn], headers)
        actual = result.row
        assert not result.error
        assert actual.get("MANUFACTURER_PART_NUMBER") == mpn
        assert actual.get("BRAND_NAME")
        assert actual.get("MOBILE_DESC") or actual.get("SHORT_DESC")
        compare_rows(expected, actual, mpn)
