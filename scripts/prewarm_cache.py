#!/usr/bin/env python3
"""Pre-warm manufacturer evidence cache for rows with resolvable brand domains."""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_INPUT
from identity.brand_resolver import resolve_identity
from ingest.csv_io import read_input_rows
from ingest.input_analyzer import analyze_input_row, catalog_search_mpn
from sources.live_enrich import fetch_manufacturer_evidence


def _warm_row(row: dict[str, str]) -> tuple[str, int, str]:
    analyzed = analyze_input_row(row)
    identity = resolve_identity(
        analyzed.normalized_mpn,
        analyzed.expanded_desc,
        row.get("E1_Brand", ""),
        row.get("DIB_Brand", ""),
        row.get("Part_Manuf", ""),
        row.get("Unilog_Brand", ""),
    )
    if not identity.domains:
        return row["Mfg_Part_Num"], 0, "no_domains"
    bundle = fetch_manufacturer_evidence(
        catalog_search_mpn(analyzed.normalized_mpn, identity.brand_key),
        identity.domains,
        manufacturer_name=identity.manufacturer_name,
        brand_name=identity.brand_name or identity.brand_key,
    )
    return row["Mfg_Part_Num"], len(bundle.items), bundle.mfr_url or "no_url"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-warm evidence cache")
    parser.add_argument("--filter", choices=["all", "dishwasher", "branded"], default="branded")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rows = read_input_rows(DEFAULT_INPUT)
    if args.filter == "dishwasher":
        rows = [r for r in rows if "dishwasher" in r["Part_Desc"].lower()]
    elif args.filter == "branded":
        rows = [r for r in rows if any(
            token in r["Part_Desc"].lower()
            for token in ("dishwasher", "diablo", "milw", "3m", "whirlpool", "frigidaire", "kichler", "hunter")
        )]
    if args.limit:
        rows = rows[: args.limit]

    warmed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_warm_row, row): row for row in rows}
        for future in as_completed(futures):
            mpn, count, note = future.result()
            warmed += 1
            print(f"{mpn}: {count} items ({note})")

    print(f"Processed {warmed} rows")


if __name__ == "__main__":
    main()
