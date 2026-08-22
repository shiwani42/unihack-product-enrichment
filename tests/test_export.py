from pathlib import Path

from app.config import DEFAULT_INPUT, OUTPUT_DIR
from ingest.csv_io import load_output_headers, read_input_rows, write_output_rows
from ingest.export_io import write_output_xlsx, write_provenance_json
from pipeline import enrich_input_row


def test_xlsx_export(tmp_path: Path):
    headers = load_output_headers()
    rows = read_input_rows(DEFAULT_INPUT)[:3]
    enriched = [enrich_input_row(row, headers).row for row in rows]
    path = tmp_path / "out.xlsx"
    write_output_xlsx(path, headers, enriched)
    assert path.exists()
    assert path.stat().st_size > 0


def test_provenance_export(tmp_path: Path):
    headers = load_output_headers()
    row = read_input_rows(DEFAULT_INPUT)[0]
    result = enrich_input_row(row, headers)
    path = tmp_path / "prov.json"
    write_provenance_json(
        path,
        [{"mpn": row["Mfg_Part_Num"], "field_sources": result.field_sources, "category_id": result.category_id}],
    )
    assert path.exists()
