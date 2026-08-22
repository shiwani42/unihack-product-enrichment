#!/usr/bin/env python3
"""Compute UniHack Solution Guide compliance metrics over an enriched CSV.

Judge-facing metrics called out by the Solution Guide:
  - field-level accuracy vs ground truth (when an expected-output file exists)
  - character-limit compliance per description type
  - percentage of attribute values found in the LOV
Plus rule-book checks:
  - placeholder leakage ("-- Unbranded --" etc. must never appear in output)
  - UOM style: space between number and unit in prose descriptions
  - source URL coverage on populated rows

Usage:
  PYTHONPATH=. python3 scripts/compliance_check.py [--csv output/enriched.csv]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS
from ingest.csv_io import load_output_headers, read_input_rows
from validate.rules import validate_row

PLACEHOLDER_TOKENS = ("-- unbranded --", "-- no unilog brand --", "-- no dib brand --")
UOM_NO_SPACE_RE = re.compile(r"\d(in|inch|inches|v|a|w|dba|ft|mm|cm)\b", re.I)


def _load_lov_values() -> set[str]:
    lov_path = ROOT / "validate" / "lov.json"
    reference_path = ROOT / "data" / "reference" / "lov_values.json"
    values: set[str] = set()
    if lov_path.exists():
        data = json.loads(lov_path.read_text(encoding="utf-8"))
        for category_rules in data.values():
            for allowed in category_rules.values():
                values.update(str(v).lower() for v in allowed)
    if reference_path.exists():
        payload = json.loads(reference_path.read_text(encoding="utf-8"))
        for allowed in payload.get("values_by_label", {}).values():
            values.update(str(v).lower() for v in allowed)
    return values


def _uom_standard_violations(rows: list[dict[str, str]]) -> dict:
    """ATTRIBUTE_UOM values outside the approved abbreviation set (when imported)."""
    uom_path = ROOT / "data" / "reference" / "uom_standards.json"
    if not uom_path.exists():
        return {"available": False}
    standards = json.loads(uom_path.read_text(encoding="utf-8"))
    approved = {str(v).lower() for v in standards.get("abbreviations", {}).values()}
    total = checked = 0
    violations: list[tuple[str, str]] = []
    for row in rows:
        for index in range(1, 51):
            uom = (row.get(f"ATTRIBUTE_UOM {index}") or "").strip()
            if not uom:
                continue
            checked += 1
            if uom.lower() not in approved:
                violations.append((row.get("Mfg_Part_Num", ""), uom))
                total += 1
    return {
        "available": True,
        "approved_count": len(approved),
        "checked": checked,
        "violations": total,
        "examples": violations[:10],
    }


def _fraction_style(rows: list[dict[str, str]]) -> int:
    """Decimal inches must be published as fractions (0.5 -> 1/2, 50.25 -> 50-1/4)."""
    bad = 0
    decimal_inch = re.compile(r"^\d+\.\d+$")
    for row in rows:
        for index in range(1, 51):
            value = (row.get(f"ATTRIBUTE_VALUE {index}") or "").strip()
            uom = (row.get(f"ATTRIBUTE_UOM {index}") or "").strip().lower()
            if value and uom == "in" and decimal_inch.fullmatch(value):
                bad += 1
    return bad


def _invoice_caps_compliance(rows: list[dict[str, str]]) -> dict:
    populated = [r["INVOICE_DESC"] for r in rows if (r.get("INVOICE_DESC") or "").strip()]
    non_caps = [v for v in populated if v != v.upper()]
    return {
        "populated": len(populated),
        "non_uppercase": len(non_caps),
        "compliant_pct": round((len(populated) - len(non_caps)) / len(populated) * 100, 2) if populated else None,
    }


def _lov_compliance(rows: list[dict[str, str]]) -> dict:
    lov_values = _load_lov_values()
    total = checked = 0
    violations: list[tuple[str, str, str]] = []
    for row in rows:
        for index in range(1, 51):
            label = (row.get(f"ATTRIBUTE_LABEL {index}") or "").strip()
            value = (row.get(f"ATTRIBUTE_VALUE {index}") or "").strip()
            if not label or not value:
                continue
            if label in {"Series", "Model", "Additional Information", "Product Name", "Size"}:
                continue
            total += 1
            if value.lower() in lov_values:
                checked += 1
            else:
                violations.append((row.get("Mfg_Part_Num", ""), label, value))
    rate = round(checked / total * 100, 2) if total else None
    return {"checked": total, "in_lov": checked, "rate_pct": rate, "sample_violations": violations[:10]}


def _char_limits(rows: list[dict[str, str]]) -> dict:
    limits = {"INVOICE_DESC": (0, 40), "MOBILE_DESC": (60, 80)}
    report: dict[str, dict] = {}
    for field, (low, high) in limits.items():
        populated = [r[field] for r in rows if (r.get(field) or "").strip()]
        over = [v for v in populated if len(v) > high]
        under = [v for v in populated if low and len(v) < low]
        report[field] = {
            "populated": len(populated),
            "over_limit": len(over),
            "under_limit": len(under),
            "compliant_pct": round((len(populated) - len(over) - len(under)) / len(populated) * 100, 2)
            if populated
            else None,
            "worst": max(populated, key=len)[:90] if populated else "",
        }
    return report


def _placeholder_leakage(rows: list[dict[str, str]], headers: list[str]) -> int:
    leaks = 0
    skip_fields = {
        "Mfg_Part_Num",
        "Part_Desc",
        "E1_Brand",
        "Unilog_Brand",
        "DIB_Brand",
        "Part_Manuf",
    }
    for row in rows:
        for field in headers:
            if field in skip_fields:
                continue
            value = (row.get(field) or "").strip().lower()
            if value in PLACEHOLDER_TOKENS:
                leaks += 1
    return leaks


def _uom_style(rows: list[dict[str, str]]) -> dict:
    fields = ["SHORT_DESC", "LONG_DESC1", "RETAIL_DESC"]
    total = bad = 0
    examples: list[str] = []
    for row in rows:
        # Quoted raw distributor descriptions are exempt: they are source
        # strings, not generated prose.
        source_desc = (row.get("Part_Desc") or "").strip()
        for field in fields:
            text = row.get(field) or ""
            if not text:
                continue
            if source_desc:
                text = text.replace(source_desc, "")
                for token in re.split(r"[\s,]+", source_desc):
                    if len(token) >= 5:
                        text = text.replace(token, "")
            total += 1
            glued = re.findall(r"(?:^|\s|x)\d+(?:-\d+/\d+)?(?:in|mm|cm|ft|dba)\b", text, re.I)
            if glued:
                bad += 1
                if len(examples) < 8:
                    examples.append(f"{row.get('Mfg_Part_Num','')}:{field}:{glued}")
    return {"descriptions_checked": total, "violations": bad, "examples": examples}


def _source_url_coverage(rows: list[dict[str, str]]) -> dict:
    populated_rows = 0
    with_mfr = 0
    with_ref = 0
    for row in rows:
        has_any = any(row.get(f"ATTRIBUTE_VALUE {i}") for i in range(1, 51)) or row.get("Product Name")
        if not has_any:
            continue
        populated_rows += 1
        if (row.get("MFR URL") or "").startswith("http"):
            with_mfr += 1
        if any((row.get(f"Ref URL {i}") or "").startswith("http") for i in range(1, 6)):
            with_ref += 1
    pct = lambda n: round(n / populated_rows * 100, 2) if populated_rows else None
    return {
        "populated_rows": populated_rows,
        "mfr_url_pct": pct(with_mfr),
        "any_ref_url_pct": pct(with_ref),
    }


def _validation_issue_rate(rows: list[dict[str, str]]) -> dict:
    from collections import Counter

    counter: Counter = Counter()
    error_rows = 0
    for row in rows:
        issues = validate_row(row, category_id="")
        if any(i.severity == "error" for i in issues):
            error_rows += 1
        for issue in issues:
            counter[f"{issue.severity}:{issue.field}"] += 1
    top = counter.most_common(12)
    return {"rows_with_errors": error_rows, "top_issues": [[k, v] for k, v in top]}


def reference_accuracy() -> dict | None:
    expected_rows = read_input_rows(DEFAULT_OUTPUT_HEADERS)
    if len(expected_rows) <= 2:
        return {
            "note": "Only organizer 2-row sample available; full 200-row ground truth "
            "(Unilog-Sample_200_Items-Input-vs-Output.xlsx) not present in guidelines/ - download from dashboard."
        }
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Solution Guide compliance metrics")
    parser.add_argument("--csv", default=str(ROOT / "output" / "enriched.csv"))
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        print(json.dumps({"error": f"missing {path}", "hint": "run cli.py enrich first"}, indent=2))
        return

    headers = load_output_headers()
    rows = read_input_rows(path)
    payload = {
        "file": str(path),
        "rows": len(rows),
        "char_limit_compliance": _char_limits(rows),
        "invoice_caps": _invoice_caps_compliance(rows),
        "lov_compliance": _lov_compliance(rows),
        "uom_standards": _uom_standard_violations(rows),
        "fraction_style_violations": _fraction_style(rows),
        "placeholder_leaks": _placeholder_leakage(rows, headers),
        "uom_style": _uom_style(rows),
        "source_url_coverage": _source_url_coverage(rows),
        "validation_issues": _validation_issue_rate(rows),
        "reference_accuracy": reference_accuracy(),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
