#!/usr/bin/env python3
"""Demo stress test: find weak spots across categories and row types."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_INPUT
from classify.category_router import route_category
from identity.brand_resolver import resolve_identity
from ingest.csv_io import load_output_headers, read_input_rows
from pipeline import enrich_input_row

OUTPUT = ROOT / "output" / "demo_audit.json"


def audit():
    headers = load_output_headers()
    rows = read_input_rows(DEFAULT_INPUT)
    results = []

    by_category: dict[str, list] = defaultdict(list)
    issue_counter: Counter = Counter()
    identity_fail = []
    mobile_short = []
    no_mfr_url_dishwasher = []
    generic_heavy = []
    pipeline_errors = []

    for row in rows:
        mpn = row["Mfg_Part_Num"]
        desc = row["Part_Desc"]
        identity = resolve_identity(
            mpn, desc, row.get("E1_Brand", ""), row.get("DIB_Brand", "")
        )
        template = route_category(desc, identity.brand_key)
        result = enrich_input_row(row, headers)

        filled = sum(1 for v in result.row.values() if (v or "").strip())
        issue_msgs = [f"{i.field}: {i.message}" for i in result.issues]

        entry = {
            "mpn": mpn,
            "desc": desc[:80],
            "category": result.category_id,
            "confidence": result.confidence_band,
            "filled": filled,
            "evidence": result.evidence_count,
            "issues": issue_msgs,
            "brand": result.row.get("BRAND_NAME", ""),
            "manufacturer": result.row.get("MANUFACTURER_NAME", ""),
            "identity_method": identity.method,
            "identity_conf": identity.confidence,
            "has_mfr_url": bool(result.row.get("MFR URL")),
            "mobile_len": len(result.row.get("MOBILE_DESC", "")),
            "error": result.error,
        }
        results.append(entry)
        by_category[result.category_id].append(entry)

        for msg in issue_msgs:
            issue_counter[msg.split(":")[0]] += 1

        if not identity.manufacturer_name and not identity.brand_name:
            identity_fail.append(mpn)
        if result.row.get("MOBILE_DESC") and len(result.row["MOBILE_DESC"]) < 60:
            mobile_short.append(mpn)
        if result.category_id == "built_in_dishwasher" and not result.row.get("MFR URL"):
            no_mfr_url_dishwasher.append(mpn)
        if result.category_id == "generic_industrial" and filled < 20:
            generic_heavy.append(mpn)
        if result.error:
            pipeline_errors.append({"mpn": mpn, "error": result.error})

    def cat_stats(cat_id: str) -> dict:
        items = by_category.get(cat_id, [])
        if not items:
            return {"count": 0}
        fills = [i["filled"] for i in items]
        ev = [i["evidence"] for i in items]
        conf = Counter(i["confidence"] for i in items)
        return {
            "count": len(items),
            "avg_filled": round(sum(fills) / len(fills), 1),
            "min_filled": min(fills),
            "max_filled": max(fills),
            "avg_evidence": round(sum(ev) / len(ev), 2),
            "confidence": dict(conf),
            "sample_weak": sorted(items, key=lambda x: x["filled"])[:3],
        }

    categories = sorted(by_category.keys())
    summary = {
        "total_rows": len(rows),
        "categories": {c: cat_stats(c) for c in categories},
        "identity_unknown_count": len(identity_fail),
        "identity_unknown_samples": identity_fail[:10],
        "mobile_below_60_count": len(mobile_short),
        "mobile_below_60_samples": mobile_short[:10],
        "dishwasher_no_mfr_url": no_mfr_url_dishwasher,
        "generic_low_fill_count": len(generic_heavy),
        "generic_low_fill_samples": generic_heavy[:10],
        "pipeline_errors": pipeline_errors,
        "top_issue_fields": issue_counter.most_common(15),
        "confidence_overall": dict(Counter(r["confidence"] for r in results)),
        "worst_20_rows": sorted(results, key=lambda x: x["filled"])[:20],
        "best_non_golden": sorted(
            [r for r in results if r["mpn"] not in ("PDSH4816AF", "WDTS7024RZ")],
            key=lambda x: -x["filled"],
        )[:10],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    s = audit()
    print(json.dumps({k: v for k, v in s.items() if k not in ("worst_20_rows", "best_non_golden")}, indent=2))
    print("\n=== WORST 10 ROWS ===")
    for r in s["worst_20_rows"][:10]:
        print(f"  {r['filled']:3d} fields | {r['category']:22s} | {r['mpn']} | {r['desc'][:50]}")
    print("\n=== BEST NON-GOLDEN ===")
    for r in s["best_non_golden"][:5]:
        print(f"  {r['filled']:3d} fields | {r['category']:22s} | {r['mpn']} | ev={r['evidence']}")
