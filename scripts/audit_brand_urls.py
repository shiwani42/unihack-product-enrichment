#!/usr/bin/env python3
"""One-SKU-per-brand live check: did we land a manufacturer page or only Part_Desc?"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("UNILOG_LIVE_FETCH", "1")
os.environ.setdefault("UNILOG_WEB_SEARCH", "1")
os.environ.setdefault("UNILOG_FETCH_TIMEOUT", "10")
os.environ.setdefault("UNILOG_FETCH_URL_LIMIT", "8")
os.environ.setdefault("UNILOG_SEARCH_URL_LIMIT", "4")
os.environ.setdefault("UNILOG_PDF_URL_LIMIT", "2")

from app.config import DEFAULT_INPUT  # noqa: E402
from identity.brand_resolver import resolve_identity  # noqa: E402
from ingest.csv_io import read_input_rows  # noqa: E402
from sources.finder import candidate_mfr_urls, first_fetch_window, is_search_url  # noqa: E402
from sources.live_enrich import fetch_manufacturer_evidence  # noqa: E402
from sources.source_policy import classify_url  # noqa: E402
from app.config import FETCH_URL_LIMIT  # noqa: E402

GUESSED = ("/p/", "/products/", "/product/", "/product-support/", "/support/")


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


def _guessed_template(url: str, mpn: str) -> bool:
    low = (url or "").lower()
    token = (mpn or "").lower()
    if not token or token not in low:
        return False
    if is_search_url(url):
        return True
    return any(f"{path}{token}" in low or f"{path}{token}/" in low for path in GUESSED)


def sample_rows() -> list[dict]:
    grouped: dict[str, dict] = {}
    for row in read_input_rows(DEFAULT_INPUT):
        ident = resolve_identity(
            row.get("Mfg_Part_Num", ""),
            row.get("Part_Desc", ""),
            row.get("E1_Brand", ""),
            row.get("DIB_Brand", ""),
            row.get("Part_Manuf", ""),
            row.get("Unilog_Brand", ""),
        )
        key = ident.brand_key or ident.manufacturer_name or row["Mfg_Part_Num"]
        if key in grouped:
            continue
        grouped[key] = {**row, "_ident": ident}
    mapped = [row for row in grouped.values() if row["_ident"].domains]
    unmapped = [row for row in grouped.values() if not row["_ident"].domains]
    # Keep all mapped brands; a handful of unmapped so we see name-guess behaviour.
    picked_unmapped = unmapped[:8]
    return mapped + picked_unmapped


def main() -> None:
    rows = sample_rows()
    print(f"checking {len(rows)} SKUs (one per mapped brand + 8 unmapped)\n", flush=True)
    print(f"{'brand':22} {'mpn':18} {'items':5} {'mfr?':4} {'kind':12} url")
    summary = defaultdict(int)
    for row in rows:
        ident = row["_ident"]
        mpn = row["Mfg_Part_Num"]
        brand = (ident.brand_key or ident.manufacturer_name or "?")[:22]
        window = first_fetch_window(candidate_mfr_urls(mpn, ident.domains), FETCH_URL_LIMIT)
        bundle = fetch_manufacturer_evidence(
            mpn,
            ident.domains,
            fetch_pdfs=True,
            manufacturer_name=ident.manufacturer_name,
            brand_name=ident.brand_name or ident.brand_key,
        )
        url = bundle.mfr_url or ""
        kind = classify_url(url, ident.domains) if url else "none"
        guessed = _guessed_template(url, mpn)
        host_ok = (not ident.domains) or (url and any(d.split("/")[0] in _host(url) for d in ident.domains))
        if not url:
            bucket = "no_url"
        elif not host_ok:
            bucket = "wrong_host"
        elif guessed and len(bundle.items) < 2:
            bucket = "guess_thin"
        elif len(bundle.items) < 2:
            bucket = "thin_pdp"
        else:
            bucket = "ok"
        summary[bucket] += 1
        flag = "Y" if url else "n"
        print(
            f"{brand:22} {mpn[:18]:18} {len(bundle.items):5} {flag:4} {kind:12} {url[:88]}",
            flush=True,
        )
        if window and bucket != "ok":
            print(f"{'':22} window: {window[:4]}")
    print("\nsummary", dict(summary))


if __name__ == "__main__":
    main()
