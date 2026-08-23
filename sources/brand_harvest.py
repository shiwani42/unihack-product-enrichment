"""One SKU per brand: collect manufacturer links and teach portable URL shapes.

Live harvest writes a report under ``output/`` (links, hosts, templates) and
promotes portable product URLs into ``search_paths.json``. Per-SKU pages stay
in ``output/harvest_known_urls.json`` so the committed seed is not flooded.
Generic CMS path shapes that worked on more than one host go into
``learned_paths.json`` so a judge SKU on an unseen brand still guesses them.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.config import DEFAULT_INPUT, OUTPUT_DIR
from identity.brand_resolver import (
    MANUFACTURER_PATH,
    _load_json,
    _unusable_brand_token,
    resolve_identity,
)
from ingest.csv_io import read_input_rows
from ingest.input_analyzer import analyze_input_row, catalog_search_mpn
from io_utils import atomic_write_text
from sources.domain_discovery import host_matches_names
from sources.finder import (
    OFFICIAL_PATHS,
    SEARCH_PATHS,
    is_blocked_url,
    is_distributor_url,
    is_search_url,
    official_url_score,
    reset_search_path_cache,
)
from sources.learned_paths import refresh_learned_paths
from sources.url_patterns import portable_templates


def _host(url: str) -> str:
    parsed = urlparse(url or "")
    return (parsed.netloc or "").lower().removeprefix("www.")


def _search_paths() -> dict[str, list[str]]:
    from sources.finder import SEARCH_PATHS_FILE

    if not SEARCH_PATHS_FILE.exists():
        return {}
    try:
        payload = json.loads(SEARCH_PATHS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def host_has_product_template(domains: list[str], extras: dict[str, list[str]] | None = None) -> bool:
    extras = extras if extras is not None else _search_paths()
    for domain in domains or []:
        host = (domain or "").lower().removeprefix("www.")
        for key, templates in extras.items():
            if key not in host and host not in key:
                continue
            if any(not is_search_url(str(item)) for item in templates or []):
                return True
    return False


def sample_brand_rows(
    rows: list[dict[str, str]],
    scope: str = "leftover",
    mpns: list[str] | None = None,
) -> list[dict]:
    """First SKU per resolved brand, filtered by harvest scope or an explicit MPN list."""
    extras = _search_paths()

    def _annotate(row: dict) -> dict:
        ident = resolve_identity(
            row.get("Mfg_Part_Num", ""),
            row.get("Part_Desc", ""),
            row.get("E1_Brand", ""),
            row.get("DIB_Brand", ""),
            row.get("Part_Manuf", ""),
            row.get("Unilog_Brand", ""),
        )
        mapped = bool(ident.domains)
        leftover = (not mapped) or (not host_has_product_template(ident.domains, extras))
        return {**row, "_ident": ident, "_mapped": mapped, "_leftover": leftover}

    if mpns:
        wanted = {(item or "").strip().upper() for item in mpns if item}
        picked: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            mpn = (row.get("Mfg_Part_Num") or "").strip().upper()
            if not mpn or mpn not in wanted or mpn in seen:
                continue
            picked.append(_annotate(row))
            seen.add(mpn)
        return picked

    grouped: dict[str, dict] = {}
    for row in rows:
        ident = resolve_identity(
            row.get("Mfg_Part_Num", ""),
            row.get("Part_Desc", ""),
            row.get("E1_Brand", ""),
            row.get("DIB_Brand", ""),
            row.get("Part_Manuf", ""),
            row.get("Unilog_Brand", ""),
        )
        label = (ident.brand_key or ident.manufacturer_name or "").strip()
        if not label or _unusable_brand_token(label):
            continue
        key = label
        if key in grouped:
            continue
        mapped = bool(ident.domains)
        leftover = (not mapped) or (not host_has_product_template(ident.domains, extras))
        grouped[key] = {
            **row,
            "_ident": ident,
            "_mapped": mapped,
            "_leftover": leftover,
        }
    picked = list(grouped.values())
    if scope == "unmapped":
        picked = [row for row in picked if not row["_mapped"]]
    elif scope == "mapped":
        picked = [row for row in picked if row["_mapped"]]
    elif scope == "leftover":
        picked = [row for row in picked if row["_leftover"]]
    elif scope != "all":
        raise ValueError(f"unknown harvest scope: {scope}")
    return picked


def _isolate_known_urls(dest: Path) -> None:
    import sources.known_urls as known_urls

    dest.parent.mkdir(parents=True, exist_ok=True)
    known_urls.KNOWN_URLS_FILE = dest
    known_urls._reset_cache()


def _generic_guess_url(url: str, mpn: str) -> bool:
    """True when the URL is only an official path guess, not a discovered PDP."""
    raw = (url or "").strip()
    token = (mpn or "").strip()
    if not raw or not token:
        return False
    parsed = urlparse(raw)
    path = unquote(parsed.path or "")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    token_plain = unquote(token)
    for template in OFFICIAL_PATHS + SEARCH_PATHS:
        if raw == origin + template.format(mpn=token, search_mpn=token):
            return True
        if unquote(raw) == origin + template.format(mpn=token_plain, search_mpn=token_plain):
            return True
    lowered = path.lower().rstrip("/")
    token_l = token_plain.lower()
    return any(lowered == f"{prefix}{token_l}" for prefix in ("/p/", "/products/", "/product/", "/appliance/"))


def _scrub_thin_record(record: dict) -> dict:
    if int(record.get("items") or 0) >= 2:
        record["usable"] = True
        return record
    record["usable"] = False
    if _generic_guess_url(record.get("mfr_url") or "", record.get("fetch_mpn") or record.get("mpn") or ""):
        record["mfr_url"] = ""
        record["host"] = ""
        record["templates"] = []
        record["ref_urls"] = []
        record["guess_thin"] = True
    return record


def _write_search_paths(payload: dict[str, list[str]]) -> None:
    from sources.finder import SEARCH_PATHS_FILE

    atomic_write_text(
        SEARCH_PATHS_FILE,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    reset_search_path_cache()


def drop_thin_promotions(before: dict[str, list[str]], records: list[dict]) -> list[str]:
    """Undo host templates taught by thin/guessed pages so junk {name}.com does not stick."""
    current = _search_paths()
    rich_hosts = {
        str(record.get("host") or "")
        for record in records
        if record.get("host") and int(record.get("items") or 0) >= 2
    }
    dropped: list[str] = []
    for record in records:
        host = str(record.get("host") or "")
        if not host or host in rich_hosts or int(record.get("items") or 0) >= 2:
            continue
        if host in before:
            if current.get(host) != before.get(host):
                current[host] = list(before[host])
                dropped.append(host)
        elif host in current:
            current.pop(host, None)
            dropped.append(host)
    if dropped:
        _write_search_paths(current)
    return dropped


def harvest_one(row: dict) -> dict:
    ident = row["_ident"]
    analyzed = analyze_input_row(row)
    fetch_mpn = catalog_search_mpn(analyzed.normalized_mpn, ident.brand_key)
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence(
        fetch_mpn,
        ident.domains,
        manufacturer_name=ident.manufacturer_name,
        brand_name=ident.brand_name or ident.brand_key,
    )
    mfr_url = bundle.mfr_url or ""
    ref_urls = list(bundle.ref_urls or [])
    product_urls = [
        url
        for url in [mfr_url, *ref_urls]
        if url.startswith("http") and not is_search_url(url) and not is_blocked_url(url)
    ]
    templates: list[str] = []
    for url in product_urls:
        for template in portable_templates(url, fetch_mpn):
            if template not in templates:
                templates.append(template)
    host = _host(mfr_url)
    return {
        "brand_key": ident.brand_key,
        "brand_name": ident.brand_name or ident.brand_key,
        "manufacturer_name": ident.manufacturer_name,
        "mapped_domains": list(ident.domains or []),
        "mpn": row.get("Mfg_Part_Num", ""),
        "fetch_mpn": fetch_mpn,
        "items": len(bundle.items),
        "mfr_url": mfr_url,
        "ref_urls": ref_urls,
        "host": host,
        "search_page": bool(mfr_url) and is_search_url(mfr_url),
        "templates": templates,
        "leftover": bool(row.get("_leftover")),
        "mapped": bool(row.get("_mapped")),
    }


def map_proposal(record: dict) -> dict | None:
    """High-confidence unmapped brand → official host for manufacturer_map.json."""
    if record.get("mapped") or record.get("search_page"):
        return None
    brand_key = (record.get("brand_key") or "").strip()
    if not brand_key or _unusable_brand_token(brand_key):
        return None
    if int(record.get("items") or 0) < 2:
        return None
    url = record.get("mfr_url") or ""
    if not url.startswith("http") or is_blocked_url(url) or is_distributor_url(url):
        return None
    if official_url_score(url, record.get("fetch_mpn") or record.get("mpn") or "") < 40:
        return None
    host = record.get("host") or _host(url)
    names = [record.get("brand_name"), record.get("manufacturer_name"), brand_key]
    if not host or not host_matches_names(host, [name for name in names if name]):
        return None
    return {
        "brand_key": brand_key,
        "manufacturer_name": record.get("manufacturer_name") or brand_key,
        "brand_name": record.get("brand_name") or brand_key,
        "domains": [host],
        "mfr_url": url,
    }


def apply_map_proposals(proposals: list[dict]) -> list[str]:
    if not proposals:
        return []
    payload = _load_json(MANUFACTURER_PATH)
    added: list[str] = []
    changed = False
    for proposal in proposals:
        key = proposal["brand_key"]
        host = proposal["domains"][0]
        meta = payload.get(key)
        if meta is None:
            payload[key] = {
                "manufacturer_name": proposal["manufacturer_name"],
                "brand_name": proposal["brand_name"],
                "domains": [host],
            }
            added.append(key)
            changed = True
            continue
        domains = list(meta.get("domains") or [])
        if host not in domains:
            domains.append(host)
            meta["domains"] = domains
            payload[key] = meta
            added.append(key)
            changed = True
    if changed:
        atomic_write_text(
            MANUFACTURER_PATH,
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )
    return added


def run_harvest(
    input_path: Path,
    scope: str = "leftover",
    limit: int = 0,
    mine_only: bool = False,
    apply_map: bool = True,
    dry_run: bool = False,
    report_path: Path | None = None,
    known_urls_path: Path | None = None,
    mpns: list[str] | None = None,
) -> dict:
    rows = sample_brand_rows(read_input_rows(input_path), scope=scope, mpns=mpns)
    if limit and limit > 0:
        rows = rows[:limit]
    report = {
        "scope": scope,
        "count": len(rows),
        "mine_only": mine_only,
        "brands": [
            {
                "brand_key": row["_ident"].brand_key,
                "brand_name": row["_ident"].brand_name,
                "mpn": row.get("Mfg_Part_Num", ""),
                "mapped": row["_mapped"],
                "domains": list(row["_ident"].domains or []),
            }
            for row in rows
        ],
        "records": [],
        "learned_paths": [],
        "map_proposals": [],
        "map_applied": [],
        "dropped_hosts": [],
        "harvest_links_added": [],
    }
    if dry_run:
        return report
    if mine_only:
        report["learned_paths"] = refresh_learned_paths()
        dest = report_path or (OUTPUT_DIR / "brand_harvest.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report["report_path"] = str(dest)
        return report

    if not mine_only:
        before_paths = _search_paths()
        _isolate_known_urls(known_urls_path or (OUTPUT_DIR / "harvest_known_urls.json"))
        records = []
        for row in rows:
            ident = row["_ident"]
            brand = (ident.brand_key or ident.manufacturer_name or "?")[:22]
            print(
                f"fetching {brand:22} {row.get('Mfg_Part_Num', '')[:18]:18} ...",
                flush=True,
            )
            try:
                record = harvest_one(row)
            except Exception as exc:
                record = {
                    "brand_key": ident.brand_key,
                    "brand_name": ident.brand_name or ident.brand_key,
                    "manufacturer_name": ident.manufacturer_name,
                    "mapped_domains": list(ident.domains or []),
                    "mpn": row.get("Mfg_Part_Num", ""),
                    "fetch_mpn": "",
                    "items": 0,
                    "mfr_url": "",
                    "ref_urls": [],
                    "host": "",
                    "search_page": False,
                    "templates": [],
                    "leftover": bool(row.get("_leftover")),
                    "mapped": bool(row.get("_mapped")),
                    "error": str(exc),
                }
            records.append(record)
            print(
                f"{brand:22} {record['mpn'][:18]:18} {record['items']:5} "
                f"{record['mfr_url'][:88]}",
                flush=True,
            )
        report["dropped_hosts"] = drop_thin_promotions(before_paths, records)
        report["records"] = [_scrub_thin_record(dict(record)) for record in records]
        extra_mpn_urls: dict[str, list[str]] = defaultdict(list)
        for record in report["records"]:
            key = record.get("fetch_mpn") or record.get("mpn")
            for url in [record.get("mfr_url"), *(record.get("ref_urls") or [])]:
                if url:
                    extra_mpn_urls[key].append(url)
        report["learned_paths"] = refresh_learned_paths(extra_mpn_urls=dict(extra_mpn_urls))
        from sources.harvest_links import remember_harvest_records

        report["harvest_links_added"] = remember_harvest_records(report["records"])
        proposals = [item for item in (map_proposal(record) for record in report["records"]) if item]
        report["map_proposals"] = proposals
        if apply_map:
            report["map_applied"] = apply_map_proposals(proposals)

    dest = report_path or (OUTPUT_DIR / "brand_harvest.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["report_path"] = str(dest)
    return report


def cmd_harvest(args: argparse.Namespace) -> None:
    os.environ.setdefault("UNILOG_LIVE_FETCH", "1")
    os.environ.setdefault("UNILOG_WEB_SEARCH", "1")
    os.environ.setdefault("UNILOG_WIKIDATA", "1")
    os.environ.setdefault("UNILOG_FETCH_TIMEOUT", "10")
    os.environ.setdefault("UNILOG_FETCH_URL_LIMIT", "8")
    os.environ.setdefault("UNILOG_SEARCH_URL_LIMIT", "4")
    os.environ.setdefault("UNILOG_PDF_URL_LIMIT", "2")
    os.environ.setdefault("UNILOG_HTTP_RETRIES", "1")
    if not getattr(args, "playwright", False):
        os.environ.setdefault("UNILOG_PLAYWRIGHT", "0")
    report = run_harvest(
        Path(args.input),
        scope=args.scope,
        limit=args.limit,
        mine_only=args.mine_only,
        apply_map=args.apply_map and not args.mine_only and not args.dry_run,
        dry_run=args.dry_run,
        report_path=Path(args.report) if args.report else None,
        mpns=args.mpn or None,
    )
    if args.dry_run:
        print(f"would fetch {report['count']} brands (scope={report['scope']})", flush=True)
        for brand in report["brands"]:
            flag = "mapped" if brand["mapped"] else "unmapped"
            print(f"{(brand['brand_key'] or '?'):22} {brand['mpn'][:18]:18} {flag:9} {','.join(brand['domains'][:2])}", flush=True)
    print(json.dumps(
        {
            "scope": report["scope"],
            "count": report["count"],
            "learned_paths": report["learned_paths"],
            "map_applied": report.get("map_applied") or [],
            "harvest_links_added": report.get("harvest_links_added") or [],
            "report_path": report.get("report_path", ""),
        },
        indent=2,
    ))


def build_harvest_parser(sub: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    if sub is not None:
        parser = sub.add_parser(
            "harvest-brands",
            help="One SKU per leftover brand: collect manufacturer links and teach URL shapes",
        )
    else:
        parser = argparse.ArgumentParser(
            description="Harvest manufacturer links and portable URL templates"
        )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument(
        "--scope",
        choices=["leftover", "unmapped", "mapped", "all"],
        default="leftover",
        help="leftover = no mapped domain or no portable product template yet",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--mpn", action="append", default=[], help="Harvest this MPN (repeatable); ignores --scope")
    parser.add_argument("--mine-only", action="store_true", help="Rebuild learned_paths.json from existing URLs")
    parser.add_argument("--dry-run", action="store_true", help="List brands that would be fetched")
    parser.add_argument("--report", default=str(OUTPUT_DIR / "brand_harvest.json"))
    parser.add_argument(
        "--apply-map",
        dest="apply_map",
        action="store_true",
        default=True,
        help="Write high-confidence unmapped hosts into manufacturer_map.json",
    )
    parser.add_argument("--no-apply-map", dest="apply_map", action="store_false")
    parser.add_argument("--playwright", action="store_true", help="Allow a Playwright fetch (off by default)")
    parser.set_defaults(func=cmd_harvest)
    return parser
