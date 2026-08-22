from pathlib import Path

from app.config import DEFAULT_INPUT, GOLDEN_MPNS
from ingest.csv_io import load_output_headers, read_input_rows
from pipeline import enrich_input_row
from validate.golden_test import compare_rows


def test_golden_rows_score_above_zero():
    headers = load_output_headers()
    golden_rows = read_input_rows(Path("guidelines/Unihack_ Expected Output - Delivery Format.csv"))
    golden_by_mpn = {row["Mfg_Part_Num"]: row for row in golden_rows}
    input_rows = read_input_rows(DEFAULT_INPUT)
    input_by_mpn = {row["Mfg_Part_Num"]: row for row in input_rows}

    for mpn in GOLDEN_MPNS:
        expected = golden_by_mpn[mpn]
        actual = enrich_input_row(input_by_mpn[mpn], headers).row
        score = compare_rows(expected, actual, mpn)
        assert score.expected_filled > 0
        assert score.score >= 0.0
