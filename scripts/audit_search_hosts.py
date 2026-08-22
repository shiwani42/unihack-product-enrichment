"""Summarize product hosts from live enrich — do not bulk-scrape search engines.

This network cannot reach DuckDuckGo, Bing returns 202/403 or localized junk,
and Brave 429s on IPv6. Host intelligence must come from product URLs that
live enrich already persists into known_urls.json (and host templates in
search_paths.json). Default mode only reads those files.

Live search is opt-in (``--search --limit N``) for a network that can reach an
engine. It uses the same IPv4-first collector as enrichment, with backoff.
Refuse a 999-MPN scrape unless ``--all`` is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from app.config import DEFAULT_INPUT
from ingest.csv_io import read_input_rows
from sources.known_urls import remembered_catalog
from sources.web_search import cite_to_url, collect_search_result_urls, unwrap_search_href

OUT = Path(__file__).resolve().parents[1] / "data" / "search_host_audit.json"
SEARCH_SLEEP_SEC = 1.0
SEARCH_SLEEP_CAP_SEC = 16.0


def unwrap(href: str) -> str:
    return unwrap_search_href(href)


def result_urls(html: str) -> list[str]:
    from sources.web_search import parse_search_result_urls

    return parse_search_result_urls(html)


def hostname(url: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def registrable(host: str) -> str:
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and parts[-2] in {"co", "com", "net", "org", "ac", "gov"}:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def rows_from_known_urls(mpns: list[str] | None = None) -> list[dict]:
    """Hosts already learned by live enrich. No search-engine requests."""
    catalog = remembered_catalog()
    keys = mpns if mpns is not None else list(catalog)
    rows: list[dict] = []
    for mpn in keys:
        urls = [url for url in catalog.get(mpn, []) if url]
        hosts = [hostname(url) for url in urls if hostname(url)]
        rows.append(
            {
                "mpn": mpn,
                "status": 200 if hosts else 0,
                "urls": urls[:20],
                "hosts": hosts,
                "source": "known_urls",
            }
        )
    return rows


async def search_one(mpn: str, manufacturer_name: str = "") -> dict:
    urls = await collect_search_result_urls(mpn, manufacturer_name=manufacturer_name, limit=20)
    hosts = [hostname(url) for url in urls if hostname(url)]
    status = 200 if urls else 0
    return {
        "mpn": mpn,
        "status": status,
        "urls": urls[:20],
        "hosts": hosts,
        "name": manufacturer_name,
        "source": "search",
    }


async def run_search(
    mpns: list[str],
    prior: dict,
    persist: bool = True,
    names: dict[str, str] | None = None,
) -> dict:
    names = names or {}
    done = {row["mpn"]: row for row in prior.get("rows", []) if row.get("hosts")}
    remaining = [mpn for mpn in mpns if mpn not in done]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    delay = SEARCH_SLEEP_SEC
    for mpn in remaining:
        row = await search_one(mpn, names.get(mpn, ""))
        done[row["mpn"]] = row
        payload = {"rows": list(done.values())}
        if persist:
            OUT.write_text(json.dumps(payload), encoding="utf-8")
        hits = sum(1 for item in done.values() if item.get("hosts"))
        print(f"saved {len(done)}/{len(mpns)} hits={hits} last={mpn} n={len(row['urls'])}", flush=True)
        if row.get("hosts"):
            delay = SEARCH_SLEEP_SEC
        else:
            delay = min(delay * 2, SEARCH_SLEEP_CAP_SEC)
        await asyncio.sleep(delay)
    return {"rows": [done[mpn] for mpn in mpns if mpn in done]}


def summarize(payload: dict) -> dict:
    host_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    hits = 0
    empty = 0
    for row in payload["rows"]:
        hosts = row.get("hosts") or []
        if not hosts:
            empty += 1
            continue
        hits += 1
        seen: set[str] = set()
        for host in hosts:
            key = registrable(host)
            if key in seen:
                continue
            seen.add(key)
            host_counts[key] += 1
            label_counts[key.split(".")[0]] += 1
    return {
        "mpns": len(payload["rows"]),
        "with_hits": hits,
        "empty": empty,
        "source": payload.get("source") or "known_urls",
        "hosts": host_counts.most_common(150),
        "labels": label_counts.most_common(150),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search",
        action="store_true",
        help="Hit search engines (IPv4 + backoff). Default only reads known_urls.json.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Cap live-search MPNs.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Allow live search of every sample MPN. Refused without this or --limit.",
    )
    return parser.parse_args(argv)


def refuse_bulk_search(search: bool, limit: int, all_mpns: bool) -> str | None:
    if search and not limit and not all_mpns:
        return "refusing to bulk-scrape search engines; pass --limit N or --all"
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    blocked = refuse_bulk_search(args.search, args.limit, args.all)
    if blocked:
        print(blocked, file=sys.stderr)
        return 2
    rows = read_input_rows(DEFAULT_INPUT)
    names = {
        row["Mfg_Part_Num"]: (row.get("DIB_Brand") or row.get("Part_Manuf") or "")
        for row in rows
        if row.get("Mfg_Part_Num")
    }
    mpns = list(dict.fromkeys(row["Mfg_Part_Num"] for row in rows if row.get("Mfg_Part_Num")))
    if args.limit:
        mpns = mpns[: args.limit]
    if args.search:
        prior = {}
        if OUT.exists() and not args.limit:
            try:
                prior = json.loads(OUT.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                prior = {}
        payload = asyncio.run(run_search(mpns, prior, persist=not bool(args.limit), names=names))
        payload["source"] = "search"
    else:
        selected = mpns if args.limit else None
        payload = {"rows": rows_from_known_urls(selected), "source": "known_urls"}
    summary = summarize(payload)
    payload["summary"] = summary
    if not args.limit:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
