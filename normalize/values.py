"""Stage 6: Cleansing and normalisation of output attribute values."""

import json
import re
from pathlib import Path

from normalize.units import split_value_uom

LOV_PATH = Path(__file__).resolve().parent.parent / "validate" / "lov.json"

FINISH_MAP = {
    "bk": "Black",
    "blk": "Black",
    "wh": "White",
    "wht": "White",
    "ss": "Stainless Steel",
    "sst": "Stainless Steel",
    "bz": "Bronze",
    "mb": "Mocha Bronze",
    "brz": "Bronze",
    "brs": "Brass",
    "chrome": "Chrome",
    "mocha": "Mocha Bronze",
}

MATERIAL_INFERENCE = {
    "Stainless Steel": "Stainless Steel",
    "Brass": "Brass",
    "Bronze": "Bronze",
    "Aluminum": "Aluminum",
    "PVC": "PVC",
    "Steel": "Steel",
}


def _load_lov() -> dict:
    if not LOV_PATH.exists():
        return {}
    return json.loads(LOV_PATH.read_text(encoding="utf-8"))


def normalize_finish(value: str) -> str:
    token = value.strip()
    if not token:
        return token
    mapped = FINISH_MAP.get(token.lower().replace(".", ""))
    return mapped or token.title()


def normalize_mounting(value: str) -> str:
    cleaned = value.strip().lower().replace("-", " ")
    if cleaned in {"built in", "builtin", "built-in", "blt in", "bltln"}:
        return "Built-in"
    if cleaned == "leg":
        return "Leg"
    return value.strip()


def lov_normalize(label: str, value: str, category_id: str) -> str:
    lov = _load_lov().get(category_id, {})
    allowed = lov.get(label, [])
    if not allowed:
        return value
    if value in allowed:
        return value
    normalized = normalize_mounting(value) if label == "Mounting Type" else value
    if normalized in allowed:
        return normalized
    for candidate in allowed:
        if candidate.lower() == normalized.lower():
            return candidate
    return normalized


def cleanse_attribute(label: str, value: str, uom: str, category_id: str) -> tuple[str, str]:
    if not value:
        return value, uom

    if label in {"Finish", "Color"}:
        return normalize_finish(value), uom
    if label == "Mounting Type":
        return normalize_mounting(value), uom
    if label in {"Voltage Rating", "Amperage Rating", "Wattage", "Sound Level", "Blade Span", "Diameter", "Length", "Width", "Size"}:
        expected = uom or {
            "Voltage Rating": "V",
            "Amperage Rating": "A",
            "Wattage": "W",
            "Sound Level": "dBA",
            "Blade Span": "in",
            "Diameter": "in",
            "Length": "in",
            "Width": "in",
        }.get(label, "")
        parsed_value, parsed_uom = split_value_uom(value, expected)
        return parsed_value, parsed_uom or uom

    return lov_normalize(label, value, category_id), uom


def impute_related_attributes(row: dict[str, str]) -> None:
    """Cross-attribute inference for empty slots."""
    label_values = {}
    for index in range(1, 51):
        label = row.get(f"ATTRIBUTE_LABEL {index}", "")
        value = row.get(f"ATTRIBUTE_VALUE {index}", "")
        if label and value:
            label_values[label] = index

    material_idx = label_values.get("Material")
    color_idx = label_values.get("Color")
    finish_idx = label_values.get("Finish")

    if material_idx and not color_idx:
        material = row.get(f"ATTRIBUTE_VALUE {material_idx}", "")
        inferred = MATERIAL_INFERENCE.get(material)
        if inferred and "Color" in [row.get(f"ATTRIBUTE_LABEL {i}", "") for i in range(1, 51)]:
            for index in range(1, 51):
                if row.get(f"ATTRIBUTE_LABEL {index}") == "Color" and not row.get(f"ATTRIBUTE_VALUE {index}"):
                    row[f"ATTRIBUTE_VALUE {index}"] = inferred
                    break

    if finish_idx and not color_idx:
        finish = row.get(f"ATTRIBUTE_VALUE {finish_idx}", "")
        for index in range(1, 51):
            if row.get(f"ATTRIBUTE_LABEL {index}") == "Color" and not row.get(f"ATTRIBUTE_VALUE {index}"):
                row[f"ATTRIBUTE_VALUE {index}"] = finish
                break


def cleanse_output_row(row: dict[str, str], category_id: str) -> None:
    for index in range(1, 51):
        label = row.get(f"ATTRIBUTE_LABEL {index}", "")
        value = row.get(f"ATTRIBUTE_VALUE {index}", "")
        uom = row.get(f"ATTRIBUTE_UOM {index}", "")
        if not label or not value:
            continue
        cleaned_value, cleaned_uom = cleanse_attribute(label, value, uom, category_id)
        row[f"ATTRIBUTE_VALUE {index}"] = cleaned_value
        row[f"ATTRIBUTE_UOM {index}"] = cleaned_uom

    impute_related_attributes(row)

    for field in ("MOBILE_DESC", "SHORT_DESC", "LONG_DESC1", "RETAIL_DESC", "INVOICE_DESC"):
        row[field] = re.sub(r"\s+", " ", row.get(field, "")).strip()
