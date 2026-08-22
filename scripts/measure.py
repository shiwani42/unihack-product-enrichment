#!/usr/bin/env python3
"""Measure enrichment quality. Run before/after changes to decide what to keep.

Offline by default (deterministic, no network variance). For an online run,
prewarm caches first:
  PYTHONPATH=. python3 scripts/prewarm_cache.py --filter branded --workers 4
  PYTHONPATH=. python3 scripts/measure.py --online --save latest

Usage:
  PYTHONPATH=. python3 scripts/measure.py
  PYTHONPATH=. python3 scripts/measure.py --save baseline
  PYTHONPATH=. python3 scripts/measure.py --save latest
  PYTHONPATH=. python3 scripts/measure.py --compare baseline latest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS, GOLDEN_MPNS, OUTPUT_DIR
from classify.category_router import route_category
from identity.brand_resolver import resolve_identity
from ingest.csv_io import load_output_headers, read_input_rows
from pipeline import enrich_input_row
from validate.golden_test import compare_rows
from validate.report import build_row_report, summarize_reports

METRICS_DIR = OUTPUT_DIR / "metrics"


def golden_metrics() -> dict:
    headers = load_output_headers()
    golden_rows = read_input_rows(DEFAULT_OUTPUT_HEADERS)
    golden_by_mpn = {row["Mfg_Part_Num"]: row for row in golden_rows if row.get("Mfg_Part_Num")}
    input_rows = read_input_rows(DEFAULT_INPUT)
    input_by_mpn = {row["Mfg_Part_Num"]: row for row in input_rows}

    benchmarks = []
    for mpn in GOLDEN_MPNS:
        expected = golden_by_mpn.get(mpn)
        source = input_by_mpn.get(mpn)
        if not expected or not source:
            continue
        actual = enrich_input_row(source, headers).row
        score = compare_rows(expected, actual, mpn)
        benchmarks.append(
            {
                "mpn": mpn,
                "score": round(score.score, 4),
                "score_pct": round(score.score * 100, 2),
                "matches": score.matches,
                "expected_filled": score.expected_filled,
                "missing_count": len(score.missing),
                "mismatch_count": len(score.mismatches),
            }
        )

    avg = sum(item["score"] for item in benchmarks) / len(benchmarks) if benchmarks else 0.0
    return {
        "benchmarks": benchmarks,
        "average_score": round(avg, 4),
        "average_pct": round(avg * 100, 2),
    }


def coverage_metrics() -> dict:
    rows = read_input_rows(DEFAULT_INPUT)
    routed = 0
    by_category: dict[str, int] = {}
    for row in rows:
        identity = resolve_identity(
            row["Mfg_Part_Num"],
            row["Part_Desc"],
            row.get("E1_Brand", ""),
            row.get("DIB_Brand", ""),
        )
        template = route_category(row["Part_Desc"], identity.brand_key)
        if template:
            routed += 1
            by_category[template.category_id] = by_category.get(template.category_id, 0) + 1
    total = len(rows)
    return {
        "total_rows": total,
        "routed_rows": routed,
        "routed_pct": round(routed / total * 100, 2) if total else 0,
        "unrouted_rows": total - routed,
        "by_category": by_category,
    }


def _enrich_reports(rows: list[dict[str, str]], headers: list[str]) -> list:
    reports = []
    for row in rows:
        result = enrich_input_row(row, headers)
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
    return reports


def batch_metrics(reports: list | None = None, limit: int | None = None) -> dict:
    headers = load_output_headers()
    rows = read_input_rows(DEFAULT_INPUT)
    if limit:
        rows = rows[:limit]

    if reports is None:
        reports = _enrich_reports(rows, headers)
    elif limit:
        reports = reports[:limit]

    summary = summarize_reports(reports)
    return {"limit": limit or len(reports), **summary}


def dishwasher_subset_metrics(reports: list | None = None) -> dict:
    if reports is None:
        headers = load_output_headers()
        rows = [row for row in read_input_rows(DEFAULT_INPUT) if "dishwasher" in row["Part_Desc"].lower()]
        if not rows:
            return {"rows": 0}
        reports = _enrich_reports(rows, headers)
    else:
        reports = [report for report in reports if report.category_id == "built_in_dishwasher"]
        if not reports:
            return {"rows": 0}
    return summarize_reports(reports)


def collect_metrics() -> dict:
    headers = load_output_headers()
    all_rows = read_input_rows(DEFAULT_INPUT)
    all_reports = _enrich_reports(all_rows, headers)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "golden": golden_metrics(),
        "coverage": coverage_metrics(),
        "batch_all": batch_metrics(reports=all_reports),
        "batch_200": batch_metrics(reports=all_reports, limit=200),
        "dishwasher_subset": dishwasher_subset_metrics(reports=all_reports),
    }


def compare_metrics(before: dict, after: dict) -> dict:
    def delta(path: str, before_val: float, after_val: float) -> dict:
        change = round(after_val - before_val, 4)
        improved = change > 0
        return {"before": before_val, "after": after_val, "delta": change, "improved": improved}

    return {
        "golden_avg_pct": delta(
            "golden",
            before["golden"]["average_pct"],
            after["golden"]["average_pct"],
        ),
        "coverage_pct": delta(
            "coverage",
            before["coverage"]["routed_pct"],
            after["coverage"]["routed_pct"],
        ),
        "batch_all_avg_filled": delta(
            "batch",
            before["batch_all"]["avg_filled_fields"],
            after["batch_all"]["avg_filled_fields"],
        ),
        "dishwasher_avg_filled": delta(
            "dishwasher",
            before["dishwasher_subset"]["avg_filled_fields"],
            after["dishwasher_subset"]["avg_filled_fields"],
        ),
        "dishwasher_high_confidence": delta(
            "dishwasher_high",
            before["dishwasher_subset"].get("confidence_breakdown", {}).get("high", 0),
            after["dishwasher_subset"].get("confidence_breakdown", {}).get("high", 0),
        ),
    }


def save_metrics(payload: dict, name: str) -> Path:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    path = METRICS_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_metrics(name: str) -> dict:
    path = METRICS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure enrichment quality")
    parser.add_argument("--save", choices=["baseline", "latest"], help="Save metrics snapshot")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="Compare two snapshots")
    parser.add_argument(
        "--online",
        action="store_true",
        help="Allow live manufacturer fetches (offline is the deterministic default)",
    )
    args = parser.parse_args()

    if not args.online:
        os.environ["UNILOG_LIVE_FETCH"] = "0"

    if args.compare:
        before = load_metrics(args.compare[0])
        after = load_metrics(args.compare[1])
        result = compare_metrics(before, after)
        print(json.dumps(result, indent=2))
        improved = all(
            item["improved"] or item["delta"] == 0
            for item in result.values()
        )
        golden_ok = result["golden_avg_pct"]["delta"] >= 0
        if improved and golden_ok:
            print("\nVERDICT: KEEP (no regressions, at least flat or better)")
        elif not golden_ok:
            print("\nVERDICT: REVERT (golden score regressed)")
        else:
            print("\nVERDICT: MIXED (review deltas)")
        return

    payload = collect_metrics()
    print(json.dumps(payload, indent=2))

    if args.save:
        path = save_metrics(payload, args.save)
        print(f"\nSaved to {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
