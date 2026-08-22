import json
from dataclasses import dataclass
from pathlib import Path

from sources.finder import is_blocked_url

LOV_PATH = Path(__file__).resolve().parent / "lov.json"
REFERENCE_LOV_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "lov_values.json"

_reference_values_cache: dict | None = None


def _load_reference_values() -> dict[str, list[str]]:
    """Organizer LOV (imported by scripts/import_references.py), label -> allowed values."""
    global _reference_values_cache
    if _reference_values_cache is None:
        cache: dict[str, list[str]] = {}
        if REFERENCE_LOV_PATH.exists():
            try:
                payload = json.loads(REFERENCE_LOV_PATH.read_text(encoding="utf-8"))
                raw = payload.get("values_by_label", {})
                cache = {str(k): [str(v) for v in vs] for k, vs in raw.items()}
            except (json.JSONDecodeError, OSError):
                cache = {}
        _reference_values_cache = cache
    return _reference_values_cache


@dataclass
class ValidationIssue:
    field: str
    message: str
    severity: str


def _load_lov() -> dict:
    if not LOV_PATH.exists():
        return {}
    return json.loads(LOV_PATH.read_text(encoding="utf-8"))


def _normalize_mounting(value: str) -> str:
    cleaned = value.strip().lower().replace("-", " ")
    if cleaned == "built in":
        return "Built-in"
    if cleaned == "leg":
        return "Leg"
    return value.strip()


def validate_row(row: dict[str, str], category_id: str = "") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    lov_all = _load_lov()
    lov = lov_all.get(category_id, {}) if category_id else {}

    invoice = row.get("INVOICE_DESC", "")
    if invoice and len(invoice) > 40:
        issues.append(ValidationIssue("INVOICE_DESC", "exceeds 40 characters", "error"))

    mobile = row.get("MOBILE_DESC", "")
    if mobile:
        if len(mobile) < 60:
            issues.append(ValidationIssue("MOBILE_DESC", "below 60 characters", "warning"))
        if len(mobile) > 80:
            issues.append(ValidationIssue("MOBILE_DESC", "exceeds 80 characters", "error"))

    short_desc = row.get("SHORT_DESC", "")
    if short_desc and len(short_desc) > 240:
        issues.append(ValidationIssue("SHORT_DESC", "exceeds recommended length", "warning"))

    for index in range(1, 51):
        label = row.get(f"ATTRIBUTE_LABEL {index}", "")
        value = row.get(f"ATTRIBUTE_VALUE {index}", "")
        uom = row.get(f"ATTRIBUTE_UOM {index}", "")

        if value and not label:
            issues.append(ValidationIssue(f"ATTRIBUTE_VALUE {index}", "value without label", "error"))

        if not value:
            continue

        constrained = {
            "Mounting Type",
            "Plug Type",
            "Color Temperature",
        }
        if label in constrained:
            check_value = _normalize_mounting(value) if label == "Mounting Type" else value
            allowed = list(lov.get(label, []) or [])
            for candidate in _load_reference_values().get(label, []):
                if candidate not in allowed:
                    allowed.append(candidate)
            if allowed and check_value not in allowed and value not in allowed:
                issues.append(
                    ValidationIssue(
                        f"ATTRIBUTE_VALUE {index}",
                        f"{label} '{value}' not in LOV",
                        "warning",
                    )
                )

        if label == "Voltage Rating" and "A" in value and "V" not in value:
            issues.append(
                ValidationIssue(
                    f"ATTRIBUTE_VALUE {index}",
                    "voltage field looks like amperage",
                    "error",
                )
            )
        if label == "Voltage Rating" and uom and uom.upper() not in {"V", "VAC", "VOLTS", ""}:
            issues.append(ValidationIssue(f"ATTRIBUTE_UOM {index}", "unexpected voltage unit", "warning"))

        if label == "Amperage Rating" and "V" in value and "A" not in value:
            issues.append(
                ValidationIssue(
                    f"ATTRIBUTE_VALUE {index}",
                    "amperage field looks like voltage",
                    "error",
                )
            )

    for field in ("MFR URL", "Ref URL 1", "Ref URL 2", "Ref URL 3", "Ref URL 4", "Ref URL 5"):
        url = (row.get(field) or "").lower()
        if url and is_blocked_url(url):
            issues.append(ValidationIssue(field, "blocked ecommerce source URL", "error"))

    if row.get("Product Name") and not row.get("Classpath"):
        issues.append(ValidationIssue("Classpath", "taxonomy missing for enriched product", "warning"))

    filled_attrs = sum(1 for i in range(1, 51) if row.get(f"ATTRIBUTE_VALUE {i}"))
    if category_id == "built_in_dishwasher" and filled_attrs == 0:
        issues.append(ValidationIssue("attributes", "no dishwasher attributes populated", "warning"))
    elif not filled_attrs:
        issues.append(ValidationIssue("attributes", "no attributes populated from evidence", "warning"))

    if row.get("Product Name"):
        missing_desc = [
            field
            for field in ("MOBILE_DESC", "SHORT_DESC", "LONG_DESC1")
            if not (row.get(field) or "").strip()
        ]
        for field in missing_desc:
            issues.append(ValidationIssue(field, "required description is empty", "error"))

    return issues


def overall_confidence(
    row: dict[str, str],
    identity_confidence: float,
    evidence_count: int,
) -> str:
    """Bands are driven by *verified* evidence counts (externally sourced items).

    Self-cited items (source_url starting with "input:") and heuristic guesses
    (smart_infer) never push a row into the "high" band on their own.
    """
    if identity_confidence < 0.4:
        return "review"
    if evidence_count >= 5 and identity_confidence >= 0.7:
        return "high"
    if evidence_count >= 3 and identity_confidence >= 0.6:
        return "high"
    if evidence_count >= 2:
        return "medium"
    if evidence_count >= 1 and identity_confidence >= 0.5:
        return "medium"
    if evidence_count >= 1:
        return "low"
    return "review"
