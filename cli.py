#!/usr/bin/env python3
import argparse
import json
import os
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS, REFERENCE_MPNS, OUTPUT_DIR
from ingest.batch_run import (
    append_report_record,
    finalize_delivery,
    prepare_output_path,
    record_from_result,
    remaining_message,
    run_meta,
)
from ingest.csv_io import (
    append_output_row,
    load_output_headers,
    output_mpn_counts,
    pending_input_rows,
    read_input_rows,
    write_output_rows,
)
from pipeline import EnrichmentResult, enrich_input_row
from validate.reference_test import compare_rows
from validate.report import summarize_reports
from validate.rules import ValidationIssue


def _failed_result(row: dict[str, str], headers: list[str], exc: BaseException) -> EnrichmentResult:
    output = {header: "" for header in headers}
    for field in ("Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"):
        output[field] = row.get(field, "")
    output["MANUFACTURER_PART_NUMBER"] = row.get("Mfg_Part_Num", "")
    return EnrichmentResult(
        row=output,
        confidence_band="review",
        evidence_count=0,
        issues=[ValidationIssue("pipeline", f"enrichment failed: {exc}", "error")],
        field_sources={},
        category_id="error",
        error=str(exc),
    )


def _enrich_rows(rows: list[dict[str, str]], headers: list[str], workers: int, on_row=None) -> list:
    if workers <= 1 or len(rows) <= 1:
        results = []
        for index, row in enumerate(rows):
            try:
                result = enrich_input_row(row, headers)
            except Exception as exc:
                result = _failed_result(row, headers, exc)
            results.append(result)
            if on_row:
                on_row(index, row, result)
        return results

    results: list | None = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(enrich_input_row, row, headers): index for index, row in enumerate(rows)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = _failed_result(rows[index], headers, exc)
            results[index] = result
            if on_row:
                on_row(index, rows[index], result)
    return results


def _record_finished(output_csv: Path, counts: Counter, lock: threading.Lock, row: dict, result) -> None:
    mpn = row.get("Mfg_Part_Num", "")
    with lock:
        counts[mpn] += 1
        append_report_record(output_csv, record_from_result(mpn, counts[mpn], result))


def _limit_rows(rows: list, limit: int) -> list:
    return rows[:limit] if limit and limit > 0 else rows


def cmd_enrich(args: argparse.Namespace) -> None:
    from scripts.import_references import ensure_official_references

    ensure_official_references()
    os.environ.setdefault("UNILOG_FETCH_BUDGET", "20000")
    headers = load_output_headers()
    input_path = Path(args.input)
    planned = read_input_rows(input_path)
    if args.limit:
        planned = _limit_rows(planned, args.limit)
    output_path = prepare_output_path(
        Path(args.output),
        run_meta(input_path, "all", args.limit or 0, len(planned)),
        fresh=bool(getattr(args, "fresh", False)),
        planned_rows=planned,
    )
    rows = pending_input_rows(planned, output_path) if args.resume else planned
    if args.resume and len(rows) != len(planned):
        print(f"Resume: skipping {len(planned) - len(rows)} rows already in {output_path}")
    if not rows:
        reports = finalize_delivery(
            planned,
            output_path,
            headers,
            xlsx=bool(args.xlsx),
            provenance=args.provenance or "",
            report_path=None,
        )
        print(f"Already complete: {len(planned)} rows in {output_path}")
        if args.xlsx:
            print(f"Wrote {len(planned)} rows to {output_path.with_suffix('.xlsx')}")
        if args.provenance:
            print(f"Wrote provenance to {args.provenance}")
        return

    total = len(rows)
    counts = output_mpn_counts(output_path)
    lock = threading.Lock()

    def on_row(index, row, result):
        print(f"{index + 1}/{total} {row.get('Mfg_Part_Num', '')} {result.confidence_band}", flush=True)
        if args.checkpoint:
            append_output_row(output_path, headers, result.row)
            _record_finished(output_path, counts, lock, row, result)

    try:
        results = _enrich_rows(rows, headers, args.workers, on_row=on_row)
    except KeyboardInterrupt:
        print(remaining_message(planned, output_path), file=sys.stderr)
        raise SystemExit(130)
    if args.dedupe:
        from dedup.canonical import collapse_duplicates

        before = len(rows)
        rows, results = collapse_duplicates(rows, results)
        print(f"Dedupe: merged {before - len(rows)} duplicate rows -> {len(rows)} unique")
    if not args.checkpoint:
        prior = read_input_rows(output_path) if args.resume and output_path.exists() else []
        write_output_rows(output_path, headers, prior + [item.row for item in results])
        for row, result in zip(rows, results):
            _record_finished(output_path, counts, lock, row, result)
    finalize_delivery(
        planned,
        output_path,
        headers,
        xlsx=bool(args.xlsx),
        provenance=args.provenance or "",
        report_path=None,
    )
    print(f"Wrote {len(planned)} rows to {output_path}")
    if args.xlsx:
        print(f"Wrote {len(planned)} rows to {output_path.with_suffix('.xlsx')}")
    if args.provenance:
        print(f"Wrote provenance to {args.provenance}")


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
    os.environ.setdefault("UNILOG_FETCH_BUDGET", "20000")
    headers = load_output_headers()
    input_path = Path(args.input)
    planned = read_input_rows(input_path)
    if args.filter == "dishwasher":
        planned = [row for row in planned if "dishwasher" in row["Part_Desc"].lower()]
    elif args.filter == "appde":
        planned = [row for row in planned if "APPDE" in row.get("Part_Manuf", "")]
    if args.limit:
        planned = _limit_rows(planned, args.limit)
    output_csv = prepare_output_path(
        Path(args.output),
        run_meta(input_path, args.filter, args.limit or 0, len(planned)),
        fresh=bool(getattr(args, "fresh", False)),
        planned_rows=planned,
    )
    rows = pending_input_rows(planned, output_csv) if args.resume else planned
    if args.resume and len(rows) != len(planned):
        print(f"Resume: skipping {len(planned) - len(rows)} rows already in {output_csv}")
    report_path = Path(args.report)

    if not rows:
        reports = finalize_delivery(
            planned,
            output_csv,
            headers,
            xlsx=bool(args.xlsx),
            provenance=args.provenance or "",
            report_path=report_path,
        )
        summary = summarize_reports(reports)
        print(f"Already complete: {len(planned)} rows in {output_csv}")
        print(f"Validation report written to {report_path}")
        print(json.dumps(summary, indent=2))
        return

    total = len(rows)
    counts = output_mpn_counts(output_csv)
    lock = threading.Lock()

    def on_row(index, row, result):
        print(f"{index + 1}/{total} {row.get('Mfg_Part_Num', '')} {result.confidence_band}", flush=True)
        if args.checkpoint:
            append_output_row(output_csv, headers, result.row)
            _record_finished(output_csv, counts, lock, row, result)

    try:
        results = _enrich_rows(rows, headers, args.workers, on_row=on_row)
    except KeyboardInterrupt:
        print(remaining_message(planned, output_csv), file=sys.stderr)
        raise SystemExit(130)

    if not args.checkpoint:
        prior = read_input_rows(output_csv) if args.resume and output_csv.exists() else []
        write_output_rows(output_csv, headers, prior + [item.row for item in results])
        for row, result in zip(rows, results):
            _record_finished(output_csv, counts, lock, row, result)

    reports = finalize_delivery(
        planned,
        output_csv,
        headers,
        xlsx=bool(args.xlsx),
        provenance=args.provenance or "",
        report_path=report_path,
    )
    leftover = pending_input_rows(planned, output_csv)
    if leftover:
        print(remaining_message(planned, output_csv))
        raise SystemExit(1)
    summary = summarize_reports(reports)
    print(f"Wrote {len(planned)} rows to {output_csv}")
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
    enrich.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip rows already checkpointed in --output (default). --no-resume redoes them.",
    )
    enrich.add_argument(
        "--checkpoint",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write each finished row immediately so a crash can resume (default).",
    )
    enrich.add_argument("--fresh", action="store_true", help="Replace existing --output instead of resuming")
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
    batch.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip rows already checkpointed in --output (default). --no-resume redoes them.",
    )
    batch.add_argument(
        "--checkpoint",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write each finished row immediately so a crash can resume (default).",
    )
    batch.add_argument("--fresh", action="store_true", help="Replace existing --output instead of resuming")
    batch.set_defaults(func=cmd_batch)

    from sources.brand_harvest import build_harvest_parser

    build_harvest_parser(sub)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
