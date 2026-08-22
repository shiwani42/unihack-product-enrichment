#!/usr/bin/env python3
"""Field-level accuracy scoring against the 200-item organizer ground truth.

Activates only after scripts/import_references.py has produced
data/reference200/input.csv and data/reference200/expected.csv (from
Unilog-Sample_200_Items-Input-vs-Output.xlsx).

For each of the 200 rows we enrich the input row and compare every non-empty
expected field, then report per-field-type accuracy - the metric the Solution
Guide says judges look for.

Usage:
  PYTHONPATH=. python3 scripts/score_ground_truth.py [--limit 0] [--offline]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data" / "reference200"

DESC_FIELDS = ["INVOICE_DESC", "MOBILE_DESC", "SHORT_DESC", "LONG_DESC1", "RETAIL_DESC"]
IDENTITY_FIELDS = ["MANUFACTURER_NAME", "BRAND_NAME", "MANUFACTURER_PART_NUMBER", "MFR URL"]
TAXONOMY_FIELDS = ["Dept", "Class", "Fine", "Classpath"]


def _load_csv(path: Path) -> list[dict[str, str]]:
    import csv as csv_mod

    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv_mod.DictReader(handle)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Score against 200-row ground truth")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offline", action="store_true", help="Disable live fetches")
    args = parser.parse_args()
    if args.offline:
        os.environ["UNILOG_LIVE_FETCH"] = "0"

    input_path = DATA_DIR / "input.csv"
    expected_path = DATA_DIR / "expected.csv"
    if not input_path.exists() or not expected_path.exists():
        print(json.dumps({
            "error": "ground truth not imported yet",
            "fix": "download Unilog-Sample_200_Items-Input-vs-Output.xlsx into guidelines/references/ then run scripts/import_references.py",
        }, indent=2))
        return

    from ingest.csv_io import load_output_headers
    from pipeline import enrich_input_row
    from validate.reference_test import compare_rows

    headers = load_output_headers()
    expected_rows = _load_csv(expected_path)
    input_rows = {r.get("Mfg_Part_Num", ""): r for r in _load_csv(input_path)}

    if args.limit:
        expected_rows = expected_rows[: args.limit]

    scores = []
    category_counter: Counter = Counter()
    for expected in expected_rows:
        mpn = expected.get("Mfg_Part_Num", "")
        source_row = input_rows.get(mpn) or next(
            (r for r in input_rows.values() if mpn and mpn in (r.get("Mfg_Part_Num") or "")), None
        )
        if not source_row:
            scores.append({"mpn": mpn, "score": 0.0, "missing_input": True})
            continue
        result = enrich_input_row(source_row, headers)
        score = compare_rows(expected, result.row, mpn)
        scores.append({
            "mpn": mpn,
            "score": round(score.score, 4),
            "matches": score.matches,
            "expected_filled": score.expected_filled,
            "category": result.category_id,
            "top_missing": score.missing[:5],
            "top_mismatch": [
                {"field": m.field, "expected": str(m.expected)[:60], "actual": str(m.actual)[:60]}
                for m in score.mismatches[:5]
            ],
        })
        category_counter[result.category_id] += 1

    valid = [s for s in scores if "score" in s]
    avg = sum(s["score"] for s in valid) / len(valid) if valid else 0.0
    payload = {
        "rows_scored": len(scores),
        "average_field_accuracy_pct": round(avg * 100, 2),
        "perfect_rows": sum(1 for s in valid if s["score"] >= 0.999),
        "by_category": dict(category_counter),
        "worst_10": sorted(valid, key=lambda s: s["score"])[:10],
        "detail_file": str(DATA_DIR / "scores.json"),
    }
    (DATA_DIR / "scores.json").write_text(json.dumps(scores, indent=1))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
