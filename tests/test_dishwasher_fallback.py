from ingest.csv_io import load_output_headers, read_input_rows
from app.config import DEFAULT_INPUT
from pipeline import enrich_input_row


def test_non_golden_dishwasher_has_attributes_and_mfr_url():
    headers = load_output_headers()
    row = next(r for r in read_input_rows(DEFAULT_INPUT) if r["Mfg_Part_Num"] == "KDFM404KPS")
    result = enrich_input_row(row, headers)
    assert result.row.get("MFR URL")
    assert result.row.get("ATTRIBUTE_VALUE 1") or result.row.get("ATTRIBUTE_VALUE 13")
    assert len(result.row.get("MOBILE_DESC", "")) >= 60
    assert result.evidence_count >= 3
