#!/usr/bin/env python3
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS, REFERENCE_MPNS, OUTPUT_DIR
from ingest.csv_io import load_output_headers, read_input_rows, write_output_rows
from ingest.export_io import write_output_xlsx, write_provenance_json
from pipeline import enrich_input_row
from validate.reference_test import compare_rows
from validate.report import build_row_report, reports_to_dicts, summarize_reports


def _enrich_rows(rows: list[dict[str, str]], headers: list[str], workers: int) -> list:
    if workers <= 1 or len(rows) <= 1:
        return [enrich_input_row(row, headers) for row in rows]

    results: list | None = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(enrich_input_row, row, headers): index for index, row in enumerate(rows)
        }
        for future in as_completed(futures):
            index = futures[future]
            results[index] = future.result()
    return results


def _limit_rows(rows: list, limit: int) -> list:
    return rows[:limit] if limit and limit > 0 else rows


def cmd_enrich(args: argparse.Namespace) -> None:
    headers = load_output_headers()
    rows = read_input_rows(Path(args.input))
    if args.limit:
        rows = _limit_rows(rows, args.limit)
    results = _enrich_rows(rows, headers, args.workers)
    if args.dedupe:
        from dedup.canonical import collapse_duplicates

        total = len(rows)
        rows, results = collapse_duplicates(rows, results)
        print(f"Dedupe: merged {total - len(rows)} duplicate rows -> {len(rows)} unique")
    enriched = [item.row for item in results]
    output_path = Path(args.output)
    write_output_rows(output_path, headers, enriched)
    print(f"Wrote {len(enriched)} rows to {output_path}")
    if args.xlsx:
        xlsx_path = output_path.with_suffix(".xlsx")
        write_output_xlsx(xlsx_path, headers, enriched)
        print(f"Wrote {len(enriched)} rows to {xlsx_path}")
    if args.provenance:
        provenance_path = Path(args.provenance)
        write_provenance_json(
            provenance_path,
            [
                {
                    "mpn": row["Mfg_Part_Num"],
                    "category_id": result.category_id,
                    "field_sources": result.field_sources,
                    "issues": [f"{i.field}: {i.message}" for i in result.issues],
                }
                for row, result in zip(rows, results)
            ],
        )
        print(f"Wrote provenance to {provenance_path}")


def cmd_reference(args: argparse.Namespace) -> None:
    headers = load_output_headers()
    reference_rows = read_input_rows(DEFAULT_OUTPUT_HEADERS)
    reference_by_mpn = {row["Mfg_Part_Num"]: row for row in reference_rows if row.get("Mfg_Part_Num")}

    input_rows = read_input_rows(DEFAULT_INPUT)
    input_by_mpn = {row["Mfg_Part_Num"]: row for row in input_rows}

    results = []
    for mpn in REFERENCE_MPNS:
        expected = reference_by_mpn.get(mpn)
        source = input_by_mpn.get(mpn)
        if not expected or not source:
            print(f"Skipping {mpn}: missing reference or input row")
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
        rows = _limit_rows(rows, args.limit)

    reports = []
    enriched_rows = []
    results = _enrich_rows(rows, headers, args.workers)
    for row, result in zip(rows, results):
        enriched_rows.append(result.row)
        reports.append(
            build_row_report(
                mpn=row["Mfg_Part_Num"],
                row=result.row,
                confidence_band=result.confidence_band,
                evidence_count=result.evidence_count,
                issues=result.issues,
                field_sources=result.field_sources,
                category_id=result.category_id,
            )
        )

    output_csv = Path(args.output)
    write_output_rows(output_csv, headers, enriched_rows)
    if args.xlsx:
        write_output_xlsx(output_csv.with_suffix(".xlsx"), headers, enriched_rows)
    if args.provenance:
        write_provenance_json(
            Path(args.provenance),
            [
                {
                    "mpn": report.mpn,
                    "category_id": report.category_id,
                    "field_sources": report.field_sources,
                    "issues": report.issues,
                }
                for report in reports
            ],
        )
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
    enrich.add_argument("--xlsx", action="store_true", help="Also write XLSX output")
    enrich.add_argument(
        "--provenance",
        default="",
        help="Write field-level source map JSON (path)",
    )
    enrich.add_argument("--workers", type=int, default=1, help="Parallel enrichment workers")
    enrich.add_argument("--dedupe", action="store_true", help="Skip duplicate MPNS in input")
    enrich.set_defaults(func=cmd_enrich)

    reference = sub.add_parser(
        "reference", aliases=["golden"],
        help="Score output against the organizer reference rows (alias: golden)",
    )
    reference.add_argument("--report", default=str(OUTPUT_DIR / "reference_report.json"))
    reference.set_defaults(func=cmd_reference)

    batch = sub.add_parser("batch", help="Batch enrich with validation report")
    batch.add_argument("--input", default=str(DEFAULT_INPUT))
    batch.add_argument("--output", default=str(OUTPUT_DIR / "batch_enriched.csv"))
    batch.add_argument("--report", default=str(OUTPUT_DIR / "batch_report.json"))
    batch.add_argument("--filter", choices=["all", "dishwasher", "appde"], default="dishwasher")
    batch.add_argument("--limit", type=int, default=0)
    batch.add_argument("--xlsx", action="store_true")
    batch.add_argument("--provenance", default=str(OUTPUT_DIR / "field_provenance.json"))
    batch.add_argument("--workers", type=int, default=4, help="Parallel enrichment workers")
    batch.set_defaults(func=cmd_batch)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
