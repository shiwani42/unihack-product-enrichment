#!/usr/bin/env python3
"""Build reference lookups from files already in the repo.

This is not a stand-in for the organizer 14k taxonomy / 161k LOV. It extracts
only values that actually appear in:

  - the 2-row gold delivery format
  - the 1,000-row sample input
  - category templates, manufacturer_map, and the built-in LOV

Official dashboard workbooks always win. If the matching xlsx is in
guidelines/references/, this script leaves that lookup alone.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS
from ingest.placeholders import clean_brand

REF_DIR = ROOT / "guidelines" / "references"
OUT_DIR = ROOT / "data" / "reference"

OFFICIAL_SOURCES = {
    "lov_values.json": "Unicat_Lov_v1_0_Updated_With_Remarks.xlsx",
    "uom_standards.json": "Unilog_Master_UOM_Standards_Abbreviations_and_Terms.xlsx",
    "manufacturers.json": "UniCat_Manufacturer_and_Brand_List.xlsx",
    "fraction_inch.json": "Decimal_Fraction.xlsx",
}

ENUMERATED_LABELS = {
    "Mounting Type",
    "Plug Type",
    "Material",
    "Color",
    "Finish",
    "Application",
    "Color Temperature",
}

NUMERIC_OR_FREE_LABELS = {
    "Voltage Rating",
    "Amperage Rating",
    "Wattage",
    "Sound Level",
    "Number of Wash Cycles",
    "Size",
    "Depth With Door Open",
    "Minimum Height",
    "Maximum Height",
    "Length",
    "Width",
    "Height",
    "Diameter",
    "Lumens",
    "Pack Quantity",
    "Model",
    "Series",
    "Additional Information",
    "Product Type",
}

GOLD_UOM = {
    "volt": "V",
    "volts": "V",
    "voltage": "V",
    "amp": "A",
    "ampere": "A",
    "amperes": "A",
    "amps": "A",
    "inch": "in",
    "inches": "in",
    "in.": "in",
    "decibel a": "dBA",
    "dba": "dBA",
    "watt": "W",
    "watts": "W",
    "foot": "ft",
    "feet": "ft",
    "millimeter": "mm",
    "millimeters": "mm",
    "pound": "lb",
    "pounds": "lb",
    "pound-force per square inch": "PSI",
    "kilowatt-hour": "kW-hr",
}

DISTRIBUTOR_MANUF_MARKERS = (
    "cooperative",
    "dealers coop",
    "lumber",
    "parksite",
    "boise cascade",
    "industrial supply",
    "donavin",
)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def official_xlsx_present(lookup_name: str) -> bool:
    source = OFFICIAL_SOURCES.get(lookup_name)
    return bool(source and (REF_DIR / source).exists())


def is_official_payload(path: Path) -> bool:
    payload = _read_json(path, {})
    source = str(payload.get("source_file") or "")
    return source in OFFICIAL_SOURCES.values()


def _should_write(lookup_name: str) -> bool:
    if official_xlsx_present(lookup_name):
        print(f"skip {lookup_name}: official workbook present")
        return False
    out = OUT_DIR / lookup_name
    if out.exists() and is_official_payload(out):
        print(f"skip {lookup_name}: already imported from organizer file")
        return False
    return True


def _write(lookup_name: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / lookup_name
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _gold_rows() -> list[dict[str, str]]:
    with DEFAULT_OUTPUT_HEADERS.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _input_rows() -> list[dict[str, str]]:
    with DEFAULT_INPUT.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def mine_lov() -> dict:
    values_by_label: dict[str, list[str]] = defaultdict(list)

    def add(label: str, value: str) -> None:
        label = (label or "").strip()
        value = (value or "").strip()
        if not label or not value:
            return
        if label in NUMERIC_OR_FREE_LABELS:
            return
        if label not in ENUMERATED_LABELS:
            return
        bucket = values_by_label[label]
        if value not in bucket:
            bucket.append(value)

    for row in _gold_rows():
        for index in range(1, 51):
            add(row.get(f"ATTRIBUTE_LABEL {index}", ""), row.get(f"ATTRIBUTE_VALUE {index}", ""))

    built_in = _read_json(ROOT / "validate" / "lov.json", {})
    for category_rules in built_in.values():
        if not isinstance(category_rules, dict):
            continue
        for label, values in category_rules.items():
            for value in values or []:
                add(label, str(value))

    for path in (ROOT / "classify" / "templates").glob("*.json"):
        template = _read_json(path, {})
        for label in template.get("attribute_labels") or []:
            values_by_label.setdefault(label, values_by_label.get(label, []))

    finish_map = {
        "Black": None,
        "White": None,
        "Stainless Steel": None,
        "Bronze": None,
        "Brass": None,
        "Aluminum": None,
        "PVC": None,
    }
    for value in finish_map:
        add("Color", value)
        add("Finish", value)
        if value in {"Stainless Steel", "Brass", "Bronze", "Aluminum", "PVC"}:
            add("Material", value)

    filtered = {key: values for key, values in sorted(values_by_label.items()) if values}
    return {
        "origin": "mined_sample",
        "source_file": DEFAULT_OUTPUT_HEADERS.name,
        "labels": len(filtered),
        "row_count": sum(len(values) for values in filtered.values()),
        "values_by_label": filtered,
        "enumerated_labels": sorted(ENUMERATED_LABELS),
        "note": "Observed enumerated values only. Not a substitute for Unicat_Lov.",
    }


def mine_uom() -> dict:
    abbreviations = dict(GOLD_UOM)
    for row in _gold_rows():
        for index in range(1, 51):
            uom = (row.get(f"ATTRIBUTE_UOM {index}") or "").strip()
            if uom:
                abbreviations.setdefault(uom.lower(), uom)
    abbrev_file = _read_json(ROOT / "ingest" / "abbreviations.json", {})
    for token, expansion in abbrev_file.items():
        if token.lower() in {"in", "ft", "mm", "lb", "psi"}:
            abbreviations.setdefault(expansion.lower(), token if token != "IN" else "in")
    return {
        "origin": "mined_sample",
        "source_file": DEFAULT_OUTPUT_HEADERS.name,
        "measurements": len(abbreviations),
        "abbreviations": abbreviations,
        "house_style_rules": [
            "space between number and unit in prose",
            "inch mixed numbers use hyphen form 50-1/4",
        ],
        "note": "Abbreviations taken from gold output and sample expansions. Not the master UOM workbook.",
    }


def mine_manufacturers() -> dict:
    seen: set[tuple[str, str]] = set()
    entries: list[dict[str, str]] = []

    def add(manufacturer_name: str, brand_name: str = "") -> None:
        mfr = (manufacturer_name or "").strip()
        brand = (brand_name or "").strip()
        if not mfr and not brand:
            return
        key = (mfr, brand)
        if key in seen:
            return
        seen.add(key)
        entry: dict[str, str] = {}
        if mfr:
            entry["manufacturer_name"] = mfr
        if brand:
            entry["brand_name"] = brand
        entries.append(entry)

    for row in _gold_rows():
        add(row.get("MANUFACTURER_NAME", ""), row.get("BRAND_NAME", ""))

    manufacturer_map = _read_json(ROOT / "identity" / "manufacturer_map.json", {})
    for meta in manufacturer_map.values():
        add(meta.get("manufacturer_name", ""), meta.get("brand_name", ""))

    for row in _input_rows():
        for field in ("DIB_Brand", "E1_Brand"):
            brand = clean_brand(row.get(field, ""))
            if not brand or brand.upper().startswith("COMMODITY"):
                continue
            add(brand, brand)
        part_manuf = clean_brand(row.get("Part_Manuf", ""))
        stripped = re.sub(r"\s*\([^)]*\)\s*$", "", part_manuf).strip()
        lowered = stripped.lower()
        if not stripped or any(marker in lowered for marker in DISTRIBUTOR_MANUF_MARKERS):
            continue
        if stripped in {"-"}:
            continue
        add(stripped, "")

    return {
        "origin": "mined_sample",
        "source_file": f"{DEFAULT_OUTPUT_HEADERS.name}+{DEFAULT_INPUT.name}",
        "count": len(entries),
        "entries": entries,
        "note": "Legal names from gold rows plus observed sample brands. Not UniCat 27k.",
    }


def mine_fractions() -> dict:
    mapping: dict[str, str] = {}

    def put(decimal: float, form: str) -> None:
        key = f"{decimal:.6f}".rstrip("0").rstrip(".")
        mapping.setdefault(key, form)

    for denom in (2, 4, 8, 16, 32, 64):
        for numer in range(1, denom):
            frac = Fraction(numer, denom)
            if frac.denominator != denom and frac.denominator < denom:
                continue
            simplified = Fraction(numer, denom)
            form = f"{simplified.numerator}/{simplified.denominator}"
            put(float(simplified), form)

    mixed_re = re.compile(r"\b(\d+)-(\d+)/(\d+)\b")
    for row in _gold_rows():
        blob = " ".join(row.values())
        for match in mixed_re.finditer(blob):
            whole, numer, denom = int(match.group(1)), int(match.group(2)), int(match.group(3))
            value = whole + (numer / denom)
            put(value, f"{whole}-{numer}/{denom}")
            put(numer / denom, f"{numer}/{denom}")

    return {
        "origin": "mined_sample",
        "source_file": DEFAULT_OUTPUT_HEADERS.name,
        "conversions": len(mapping),
        "decimal_to_fraction": dict(sorted(mapping.items(), key=lambda item: float(item[0]))),
        "note": "Closed inch-fraction table plus mixed numbers from gold rows (50-1/4).",
    }


def mine_taxonomy_coverage() -> dict:
    templates = []
    for path in sorted((ROOT / "classify" / "templates").glob("*.json")):
        data = _read_json(path, {})
        templates.append(
            {
                "template_id": data.get("category_id"),
                "classpath": data.get("classpath"),
                "dept": data.get("dept"),
                "class": data.get("class"),
                "fine": data.get("fine"),
            }
        )
    gold_classpaths = sorted({row.get("Classpath", "") for row in _gold_rows() if row.get("Classpath")})
    return {
        "origin": "mined_sample",
        "template_count": len(templates),
        "templates": templates,
        "gold_classpaths": gold_classpaths,
        "note": "Covers observed sample families only. Not the 14,000-leaf Unicat taxonomy.",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    miners = {
        "lov_values.json": mine_lov,
        "uom_standards.json": mine_uom,
        "manufacturers.json": mine_manufacturers,
        "fraction_inch.json": mine_fractions,
    }
    for name, miner in miners.items():
        if not _should_write(name):
            continue
        path = _write(name, miner())
        written.append(path.name)
        payload = json.loads(path.read_text(encoding="utf-8"))
        extra = payload.get("labels") or payload.get("measurements") or payload.get("count") or payload.get("conversions")
        print(f"{name}: {extra} -> {path}")
    coverage = mine_taxonomy_coverage()
    _write("sample_taxonomy.json", coverage)
    print(f"sample_taxonomy.json: {coverage['template_count']} templates")
    print(f"\nWrote {len(written)} mined lookups. Official xlsx files still overlay these.")


if __name__ == "__main__":
    main()
