#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS, GOLDEN_MPNS, OUTPUT_DIR
from ingest.csv_io import load_output_headers, read_input_rows, write_output_rows
from pipeline import enrich_input_row
from validate.golden_test import compare_rows
from validate.report import build_row_report, reports_to_dicts, summarize_reports


def cmd_enrich(args: argparse.Namespace) -> None:
    headers = load_output_headers()
    rows = read_input_rows(Path(args.input))
    if args.limit:
        rows = rows[: args.limit]
    enriched = [enrich_input_row(row, headers).row for row in rows]
    output_path = Path(args.output)
    write_output_rows(output_path, headers, enriched)
    print(f"Wrote {len(enriched)} rows to {output_path}")


def cmd_golden(args: argparse.Namespace) -> None:
    headers = load_output_headers()
    golden_rows = read_input_rows(DEFAULT_OUTPUT_HEADERS)
    golden_by_mpn = {row["Mfg_Part_Num"]: row for row in golden_rows if row.get("Mfg_Part_Num")}

    input_rows = read_input_rows(DEFAULT_INPUT)
    input_by_mpn = {row["Mfg_Part_Num"]: row for row in input_rows}

    results = []
    for mpn in GOLDEN_MPNS:
        expected = golden_by_mpn.get(mpn)
        source = input_by_mpn.get(mpn)
        if not expected or not source:
            print(f"Skipping {mpn}: missing golden or input row")
            continue
        actual = enrich_input_row(source, headers).row
        score = compare_rows(expected, actual, mpn)
        results.append(score)
        print(f"{mpn}: {score.matches}/{score.expected_filled} ({score.score:.1%})")
        for diff in score.mismatches[:12]:
            print(f"  mismatch {diff.field}: expected={diff.expected!r} actual={diff.actual!r}")
        for field in score.missing[:8]:
            print(f"  missing {field}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "mpn": item.mpn,
                "score": round(item.score, 4),
                "matches": item.matches,
                "expected_filled": item.expected_filled,
                "missing_count": len(item.missing),
                "mismatch_count": len(item.mismatches),
            }
            for item in results
        ]
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Report written to {report_path}")


def cmd_batch(args: argparse.Namespace) -> None:
    headers = load_output_headers()
    rows = read_input_rows(Path(args.input))
    if args.filter == "dishwasher":
        rows = [row for row in rows if "dishwasher" in row["Part_Desc"].lower()]
    elif args.filter == "appde":
        rows = [row for row in rows if "APPDE" in row.get("Part_Manuf", "")]
    if args.limit:
        rows = rows[: args.limit]

    reports = []
    enriched_rows = []
    for row in rows:
        result = enrich_input_row(row, headers)
        enriched_rows.append(result.row)
        reports.append(
            build_row_report(
                mpn=row["Mfg_Part_Num"],
                row=result.row,
                confidence_band=result.confidence_band,
                evidence_count=result.evidence_count,
                issues=result.issues,
            )
        )

    output_csv = Path(args.output)
    write_output_rows(output_csv, headers, enriched_rows)
    summary = summarize_reports(reports)
    report_payload = {"summary": summary, "rows": reports_to_dicts(reports)}
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(enriched_rows)} rows to {output_csv}")
    print(f"Validation report written to {report_path}")
    print(json.dumps(summary, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UniHack product enrichment pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    enrich = sub.add_parser("enrich", help="Enrich input CSV into delivery format")
    enrich.add_argument("--input", default=str(DEFAULT_INPUT))
    enrich.add_argument("--output", default=str(OUTPUT_DIR / "enriched.csv"))
    enrich.add_argument("--limit", type=int, default=0)
    enrich.set_defaults(func=cmd_enrich)

    golden = sub.add_parser("golden", help="Score output against golden examples")
    golden.add_argument("--report", default=str(OUTPUT_DIR / "golden_report.json"))
    golden.set_defaults(func=cmd_golden)

    batch = sub.add_parser("batch", help="Batch enrich with validation report")
    batch.add_argument("--input", default=str(DEFAULT_INPUT))
    batch.add_argument("--output", default=str(OUTPUT_DIR / "batch_enriched.csv"))
    batch.add_argument("--report", default=str(OUTPUT_DIR / "batch_report.json"))
    batch.add_argument("--filter", choices=["all", "dishwasher", "appde"], default="dishwasher")
    batch.add_argument("--limit", type=int, default=0)
    batch.set_defaults(func=cmd_batch)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
