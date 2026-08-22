#!/usr/bin/env python3
"""Import UniHack dashboard reference files into machine-readable lookups.

Drop the organizer files into guidelines/references/ (exact names below) and
run this script. Each import is optional: whatever exists gets converted to
data/reference/*.json which the rest of the pipeline consumes automatically.

Expected inputs (guidelines/references/):
  Unicat_Lov_v1_0_Updated_With_Remarks.xlsx      -> lov_values.json (~161k LOV rows)
  Unilog_Master_UOM_Standards_Abbreviations_and_Terms.xlsx -> uom_standards.json
  UniCat_Manufacturer_and_Brand_List.xlsx        -> manufacturers.json (27k rows)
  Decimal_Fraction.xlsx                          -> fraction_inch.json (63 conversions)
  Unilog-Sample_200_Items-Input-vs-Output.xlsx   -> reference200_input.csv + reference200_expected.csv

Usage:
  PYTHONPATH=. python3 scripts/import_references.py [--src guidelines/references]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REF_DIR = ROOT / "guidelines" / "references"
OUT_DIR = ROOT / "data" / "reference"
REFERENCE200_DIR = ROOT / "data" / "reference200"

PLACEHOLDER_TOKENS = {"-- unbranded --", "-- no unilog brand --", "-- no dib brand --"}


def _clean(value) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in PLACEHOLDER_TOKENS else text


def _rows(path: Path, sheet_index: int | None = None) -> list[list[str]]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[sheet_index]] if sheet_index is not None else workbook.active
        return [[_clean(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _header_row_index(rows: list[list[str]]) -> int:
    """Find the header row even with multi-row junk headers (guide warns about this)."""
    best_row, best_score = 0, -1
    for index, row in enumerate(rows[:12]):
        filled = [cell for cell in row if cell]
        if len(filled) >= 3 and len(filled) > best_score:
            best_row, best_score = index, len(filled)
    return best_row


def _header_map(rows: list[list[str]]) -> dict[str, int]:
    return {
        str(cell).strip().lower(): position
        for position, cell in enumerate(rows[_header_row_index(rows)])
        if cell
    }


def import_lov(src: Path) -> Path | None:
    path = src / "Unicat_Lov_v1_0_Updated_With_Remarks.xlsx"
    if not path.exists():
        return None
    rows = _rows(path)
    header = _header_map(rows)

    def col(*candidates: str) -> int | None:
        for name in candidates:
            if name in header:
                return header[name]
        return None

    label_col = col("attribute label", "normalized label")
    value_col = col("attribute values", "normalized values")
    classpath_col = col("classpath", "leaf node classpath")
    if label_col is None or value_col is None:
        print(f"LOV: could not locate label/value columns; headers={list(header)[:8]}")
        return None

    values_by_label: dict[str, list[str]] = {}
    header_index = _header_row_index(rows)
    for position, row in enumerate(rows):
        if position <= header_index:
            continue
        label = row[label_col] if label_col < len(row) else ""
        value = row[value_col] if value_col < len(row) else ""
        if not label or not value:
            continue
        bucket = values_by_label.setdefault(label.strip(), [])
        if value.strip() not in bucket:
            bucket.append(value.strip())
    payload = {
        "source_file": path.name,
        "row_count": sum(len(v) for v in values_by_label.values()),
        "labels": len(values_by_label),
        "values_by_label": values_by_label,
        "_classpath_col_present": classpath_col is not None,
    }
    out = OUT_DIR / "lov_values.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1))
    print(f"LOV: {payload['labels']} labels, {payload['row_count']} values -> {out.name}")
    return out


def import_uom(src: Path) -> Path | None:
    path = src / "Unilog_Master_UOM_Standards_Abbreviations_and_Terms.xlsx"
    if not path.exists():
        return None
    abbreviations: dict[str, str] = {}
    rules: list[str] = []
    for sheet_index in range(3):
        try:
            rows = _rows(path, sheet_index=sheet_index)
        except Exception:
            break
        if not rows:
            continue
        header = _header_map(rows)
        meas_col = next((header[k] for k in header if "measurement" in k or "uom type" in k), None)
        abbr_col = next((header[k] for k in header if "abbreviation" in k or "capture form" in k or "approved" in k), None)
        for row in rows[1:]:
            if meas_col is not None and abbr_col is not None and meas_col < len(row) and abbr_col < len(row):
                measurement, abbr = row[meas_col], row[abbr_col]
                if measurement and abbr:
                    abbreviations.setdefault(measurement.lower(), abbr)
                elif abbr and re.fullmatch(r"[A-Za-z/°%\"']{1,6}", abbr) and abbr not in abbreviations.values():
                    pass
        for row in rows:
            joined = " ".join(cell for cell in row if cell)
            if "space between" in joined.lower() or "hyphen" in joined.lower():
                if joined not in rules:
                    rules.append(joined[:300])
    payload = {
        "source_file": path.name,
        "measurements": len(abbreviations),
        "abbreviations": abbreviations,
        "house_style_rules": rules[:40],
    }
    out = OUT_DIR / "uom_standards.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1))
    print(f"UOM: {payload['measurements']} measurements -> {out.name}")
    return out


def import_manufacturers(src: Path) -> Path | None:
    path = src / "UniCat_Manufacturer_and_Brand_List.xlsx"
    if not path.exists():
        return None
    rows = _rows(path)
    header = _header_map(rows)
    mfr_col = next((header[k] for k in header if k.startswith("manufacturer_name")), None)
    brand_col = next((header[k] for k in header if k.startswith("brand_name")), None)
    mfr_code_col = next((header[k] for k in header if k.startswith("manufacturer_code")), None)
    if mfr_col is None:
        print(f"Manufacturers: header columns not found; got {list(header)[:8]}")
        return None
    entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows[1:]:
        mfr = row[mfr_col] if mfr_col < len(row) else ""
        brand = row[brand_col] if brand_col is not None and brand_col < len(row) else ""
        key = (mfr, brand)
        if not mfr or key in seen:
            continue
        seen.add(key)
        entry = {"manufacturer_name": mfr}
        if brand:
            entry["brand_name"] = brand
        if mfr_code_col is not None and mfr_code_col < len(row) and row[mfr_code_col]:
            entry["manufacturer_code"] = row[mfr_code_col]
        entries.append(entry)
    payload = {"source_file": path.name, "count": len(entries), "entries": entries}
    out = OUT_DIR / "manufacturers.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1))
    print(f"Manufacturers: {len(entries)} unique entries -> {out.name}")
    return out


def import_fractions(src: Path) -> Path | None:
    path = src / "Decimal_Fraction.xlsx"
    if not path.exists():
        return None
    rows = _rows(path)
    mapping: dict[str, str] = {}
    frac_re = re.compile(r"^\d+-?\d*/\d+$|^\d+/\d+$")
    dec_re = re.compile(r"^\d*\.\d+$")
    for row in rows:
        cells = [c for c in row if c]
        for i, cell in enumerate(cells):
            nxt = cells[i + 1] if i + 1 < len(cells) else ""
            if dec_re.fullmatch(cell) and frac_re.fullmatch(nxt):
                decimal = f"{float(cell):.6f}".rstrip("0").rstrip(".")
                mapping.setdefault(decimal, nxt)
            elif frac_re.fullmatch(cell) and dec_re.fullmatch(nxt):
                decimal = f"{float(nxt):.6f}".rstrip("0").rstrip(".")
                mapping.setdefault(decimal, cell)
    payload = {"source_file": path.name, "conversions": len(mapping), "decimal_to_fraction": mapping}
    out = OUT_DIR / "fraction_inch.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1))
    print(f"Fractions: {len(mapping)} conversions -> {out.name}")
    return out


def _sheet_to_csv(xlsx: Path, sheet_name_hint: list[str], out_path: Path) -> bool:
    from openpyxl import load_workbook

    workbook = load_workbook(xlsx, read_only=True, data_only=True)
    try:
        target = None
        for name in workbook.sheetnames:
            lowered = name.lower()
            if any(hint in lowered for hint in sheet_name_hint):
                target = workbook[name]
                break
        target = target or workbook[workbook.sheetnames[0]]
        import csv as csv_mod

        with out_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv_mod.writer(handle)
            for row in target.iter_rows(values_only=True):
                writer.writerow([_clean(cell) for cell in row])
        return True
    finally:
        workbook.close()


def import_reference200(src: Path) -> Path | None:
    path = src / "Unilog-Sample_200_Items-Input-vs-Output.xlsx"
    if not path.exists():
        return None
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    names = [n.lower() for n in workbook.sheetnames]
    if not names:
        print(f"Reference200: {path.name} has no sheets")
        return None
    workbook.close()

    data_dir = REFERENCE200_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    _sheet_to_csv(path, ["input"], data_dir / "input.csv")
    _sheet_to_csv(path, ["delivery", "output"], data_dir / "expected.csv")
    print(f"Reference200: wrote {data_dir/'input.csv'} and {data_dir/'expected.csv'}")
    return data_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Import dashboard reference files")
    parser.add_argument("--src", default=str(REF_DIR))
    args = parser.parse_args()
    src = Path(args.src)
    if not src.exists():
        print(f"No references directory at {src}; nothing to do.")
        print("Download the dashboard resource files into guidelines/references/ and rerun.")
        return
    results = {
        "lov": import_lov(src),
        "uom": import_uom(src),
        "manufacturers": import_manufacturers(src),
        "fractions": import_fractions(src),
        "reference200": import_reference200(src),
    }
    found = sum(1 for v in results.values() if v)
    print(f"\n{found}/5 reference sets imported.")
    missing = [k for k, v in results.items() if v is None]
    if missing:
        print("Missing inputs for:", ", ".join(missing))


if __name__ == "__main__":
    main()
