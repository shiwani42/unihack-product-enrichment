"""Crash-safe local batch: checkpoint each SKU, resume the rest, finalize the full set."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import Counter
from pathlib import Path

from ingest.csv_io import order_output_like_input, pending_input_rows, read_input_rows, write_output_rows
from ingest.export_io import write_output_xlsx, write_provenance_json
from validate.report import RowReport, build_row_report, reports_to_dicts, summarize_reports
from validate.rules import ValidationIssue, overall_confidence, validate_row

_jsonl_lock = threading.Lock()


def meta_path(output_csv: Path) -> Path:
    return Path(str(output_csv) + ".meta.json")


def reports_path(output_csv: Path) -> Path:
    return Path(str(output_csv) + ".reports.jsonl")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_meta(input_path: Path, filter_name: str, limit: int, total: int) -> dict:
    return {
        "input": str(input_path.resolve()),
        "input_sha256": file_sha256(input_path) if input_path.exists() else "",
        "filter": filter_name or "all",
        "limit": int(limit or 0),
        "total": int(total),
    }


def load_meta(output_csv: Path) -> dict:
    path = meta_path(output_csv)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_meta(output_csv: Path, meta: dict) -> None:
    path = meta_path(output_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def meta_matches(existing: dict, wanted: dict) -> bool:
    if not existing:
        return True
    return (
        existing.get("input_sha256") == wanted.get("input_sha256")
        and existing.get("filter") == wanted.get("filter")
        and int(existing.get("limit") or 0) == int(wanted.get("limit") or 0)
    )


def sibling_output(output_csv: Path, digest: str) -> Path:
    stem = output_csv.stem
    suffix = output_csv.suffix or ".csv"
    return output_csv.with_name(f"{stem}-{digest[:8]}{suffix}")


def clear_run_artifacts(output_csv: Path) -> None:
    for path in (
        output_csv,
        meta_path(output_csv),
        reports_path(output_csv),
        output_csv.with_suffix(".xlsx"),
    ):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def append_report_record(output_csv: Path, record: dict) -> None:
    path = reports_path(output_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _jsonl_lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def load_report_records(output_csv: Path) -> list[dict]:
    path = reports_path(output_csv)
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return records


def record_from_result(mpn: str, occurrence: int, result) -> dict:
    issues = []
    for issue in result.issues or []:
        if isinstance(issue, ValidationIssue):
            issues.append(f"{issue.field}: {issue.message}")
        else:
            issues.append(str(issue))
    return {
        "mpn": mpn,
        "occurrence": occurrence,
        "confidence_band": result.confidence_band,
        "evidence_count": result.evidence_count,
        "issues": issues,
        "field_sources": result.field_sources or {},
        "category_id": result.category_id,
    }


def _reconstruct_report(input_row: dict[str, str], output_row: dict[str, str]) -> RowReport:
    from classify.category_router import route_category
    from extract.cache import load_cached_bundle
    from identity.brand_resolver import resolve_identity
    from pipeline import _field_sources_from_bundle, count_verified_items

    mpn = input_row.get("Mfg_Part_Num", "")
    identity = resolve_identity(
        mpn=mpn,
        part_desc=input_row.get("Part_Desc", ""),
        e1_brand=input_row.get("E1_Brand", ""),
        dib_brand=input_row.get("DIB_Brand", ""),
        part_manuf=input_row.get("Part_Manuf", ""),
        unilog_brand=input_row.get("Unilog_Brand", ""),
    )
    template = route_category(input_row.get("Part_Desc", ""), identity.brand_key)
    bundle = load_cached_bundle(mpn)
    evidence_count = len(bundle.items) if bundle else 0
    verified = count_verified_items(bundle)
    sources = _field_sources_from_bundle(bundle, output_row) if bundle else {}
    if output_row.get("MFR URL") and "MFR URL" not in sources:
        sources["MFR URL"] = output_row["MFR URL"]
    return build_row_report(
        mpn=mpn,
        row=output_row,
        confidence_band=overall_confidence(output_row, identity.confidence, verified),
        evidence_count=evidence_count,
        issues=validate_row(output_row, category_id=template.category_id),
        field_sources=sources,
        category_id=template.category_id,
    )


def _report_from_record(record: dict, output_row: dict[str, str]) -> RowReport:
    issues = [
        ValidationIssue("pipeline", str(item), "warning") if ": " not in str(item) else ValidationIssue(
            str(item).split(": ", 1)[0],
            str(item).split(": ", 1)[1],
            "warning",
        )
        for item in record.get("issues") or []
    ]
    return build_row_report(
        mpn=record.get("mpn") or output_row.get("Mfg_Part_Num", ""),
        row=output_row,
        confidence_band=record.get("confidence_band") or "review",
        evidence_count=int(record.get("evidence_count") or 0),
        issues=issues,
        field_sources=record.get("field_sources") or {},
        category_id=record.get("category_id") or "",
    )


def assemble_reports(
    input_rows: list[dict[str, str]],
    output_rows: list[dict[str, str]],
    output_csv: Path,
) -> list[RowReport]:
    queued: dict[tuple[str, int], dict] = {}
    seen: Counter[str] = Counter()
    for record in load_report_records(output_csv):
        mpn = str(record.get("mpn") or "")
        occurrence = int(record.get("occurrence") or 0)
        if occurrence <= 0:
            seen[mpn] += 1
            occurrence = seen[mpn]
        queued[(mpn, occurrence)] = record
    used: Counter[str] = Counter()
    reports: list[RowReport] = []
    for input_row, output_row in zip(input_rows, output_rows):
        mpn = input_row.get("Mfg_Part_Num", "")
        used[mpn] += 1
        record = queued.get((mpn, used[mpn]))
        if record:
            reports.append(_report_from_record(record, output_row))
        else:
            reports.append(_reconstruct_report(input_row, output_row))
    return reports


def prepare_output_path(
    output_csv: Path,
    wanted: dict,
    fresh: bool,
    planned_rows: list[dict[str, str]] | None = None,
) -> Path:
    if fresh:
        clear_run_artifacts(output_csv)
        write_meta(output_csv, wanted)
        return output_csv
    existing = load_meta(output_csv)
    if _reuse_output(output_csv, wanted, existing, planned_rows or []):
        if not existing:
            write_meta(output_csv, wanted)
        return output_csv
    alt = sibling_output(output_csv, wanted.get("input_sha256") or "newfile")
    print(
        f"Existing {output_csv} is from a different input. "
        f"Writing this run to {alt} (pass --fresh to replace)."
    )
    if not load_meta(alt):
        write_meta(alt, wanted)
    return alt


def _reuse_output(output_csv: Path, wanted: dict, existing: dict, planned_rows: list[dict[str, str]]) -> bool:
    if existing and meta_matches(existing, wanted):
        return True
    if not output_csv.exists() or output_csv.stat().st_size == 0:
        return True
    if existing:
        return False
    from ingest.csv_io import output_mpn_counts

    counts = output_mpn_counts(output_csv)
    planned = Counter((row.get("Mfg_Part_Num") or "").strip() for row in planned_rows)
    return all(counts[mpn] <= planned[mpn] for mpn in counts)


def remaining_message(input_rows: list[dict[str, str]], output_csv: Path) -> str:
    left = pending_input_rows(input_rows, output_csv)
    done = len(input_rows) - len(left)
    return (
        f"Stopped after {done}/{len(input_rows)} rows. "
        f"Re-run the same command to resume the remaining {len(left)}."
    )


def finalize_delivery(
    input_rows: list[dict[str, str]],
    output_csv: Path,
    headers: list[str],
    *,
    xlsx: bool,
    provenance: str,
    report_path: Path | None,
) -> list[RowReport]:
    raw = read_input_rows(output_csv) if output_csv.exists() else []
    ordered = order_output_like_input(input_rows, raw, headers)
    write_output_rows(output_csv, headers, ordered)
    if xlsx:
        write_output_xlsx(output_csv.with_suffix(".xlsx"), headers, ordered)
    reports = assemble_reports(input_rows, ordered, output_csv)
    if provenance:
        write_provenance_json(
            Path(provenance),
            [
                {
                    "mpn": item.mpn,
                    "category_id": item.category_id,
                    "field_sources": item.field_sources,
                    "issues": item.issues,
                }
                for item in reports
            ],
        )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"summary": summarize_reports(reports), "rows": reports_to_dicts(reports)}
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    leftover = pending_input_rows(input_rows, output_csv)
    if leftover:
        print(remaining_message(input_rows, output_csv))
    return reports
