from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS, REFERENCE_MPNS
from ingest.csv_io import load_output_headers, read_input_rows
from pipeline import enrich_input_row
from validate.reference_test import compare_rows


def test_reference_rows_meet_target_score():
    headers = load_output_headers()
    reference_rows = read_input_rows(DEFAULT_OUTPUT_HEADERS)
    reference_by_mpn = {row["Mfg_Part_Num"]: row for row in reference_rows}
    input_rows = read_input_rows(DEFAULT_INPUT)
    input_by_mpn = {row["Mfg_Part_Num"]: row for row in input_rows}

    for mpn in REFERENCE_MPNS:
        expected = reference_by_mpn[mpn]
        actual = enrich_input_row(input_by_mpn[mpn], headers).row
        score = compare_rows(expected, actual, mpn)
        assert score.score >= 0.70, f"{mpn} score {score.score:.1%} below 70% target"
