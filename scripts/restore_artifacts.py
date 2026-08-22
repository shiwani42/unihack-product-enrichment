#!/usr/bin/env python3
"""Restore delivery artifacts in output/ from the canonical batch run.

Rebuilds field_provenance.json, enriched.xlsx, upload_output.csv and
last_report.json from batch_enriched.csv + batch_report.json (the full
1000-row online batch), overwriting any smaller stale runs.

Usage: PYTHONPATH=. python3 scripts/restore_artifacts.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_INPUT, OUTPUT_DIR  # noqa: E402
from app.ui_sections import row_preview  # noqa: E402
from ingest.csv_io import load_output_headers, read_input_rows, write_output_rows  # noqa: E402
from ingest.export_io import write_output_xlsx, write_provenance_json  # noqa: E402


def main() -> None:
    report = json.loads((OUTPUT_DIR / "batch_report.json").read_text(encoding="utf-8"))
    rows = report["rows"]
    headers = load_output_headers()
    enriched = read_input_rows(OUTPUT_DIR / "batch_enriched.csv")
    inputs = {r["Mfg_Part_Num"]: r for r in read_input_rows(DEFAULT_INPUT)}
    by_mpn = {r["mpn"]: r for r in rows}

    write_provenance_json(
        OUTPUT_DIR / "field_provenance.json",
        [
            {
                "mpn": r.get("mpn", ""),
                "category_id": r.get("category_id", ""),
                "field_sources": r.get("field_sources", {}),
                "issues": r.get("issues", []),
            }
            for r in rows
        ],
    )

    write_output_xlsx(OUTPUT_DIR / "enriched.xlsx", headers, enriched)
    shutil.copyfile(OUTPUT_DIR / "batch_enriched.csv", OUTPUT_DIR / "upload_output.csv")

    previews = []
    for row in enriched:
        mpn = row.get("Mfg_Part_Num", "")
        rep = by_mpn.get(mpn, {})
        previews.append(row_preview(row, rep, input_row=inputs.get(mpn)))
    payload = {"filter": "all", "summary": report["summary"], "rows": rows, "previews": previews}
    (OUTPUT_DIR / "last_report.json").write_text(json.dumps(payload), encoding="utf-8")

    print(f"restored: provenance={len(rows)} rows, xlsx+csv={len(enriched)} rows, "
          f"last_report previews={len(previews)}")


if __name__ == "__main__":
    main()
