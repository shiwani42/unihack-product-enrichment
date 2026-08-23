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


VOLTAGE_UOMS = frozenset({"v", "vac", "vdc", "volt", "volts"})
AMPERAGE_UOMS = frozenset({"a", "amp", "amps"})
WATTAGE_UOMS = frozenset({"w", "watt", "watts"})
STANDARD_CCTS = frozenset({"2700K", "3000K", "3500K", "4000K", "5000K", "6500K", "Multi CCT"})
PLAUSIBLE_VOLTS = frozenset(
    {12, 24, 36, 48, 110, 115, 120, 125, 208, 220, 230, 240, 277, 347, 380, 400, 415, 440, 480, 600}
)
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_TEMPLATE_JUNK = re.compile(r"\{\{|}}|attributeValue", re.I)


def _uom_family(uom: str) -> str:
    token = (uom or "").strip().lower().rstrip(".")
    if token in VOLTAGE_UOMS:
        return "voltage"
    if token in AMPERAGE_UOMS:
        return "amperage"
    if token in WATTAGE_UOMS:
        return "wattage"
    return ""


def _junk_spec_value(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if _TEMPLATE_JUNK.search(text):
        return True
    if _HEX_COLOR.fullmatch(text):
        return True
    return False


_MAINS_APPLIANCE_CATEGORIES = frozenset({"built_in_dishwasher", "cooking_range"})


def _plausible_voltage(value: str, category_id: str = "") -> bool:
    match = re.search(r"(\d+(?:\.\d+)?)", value or "")
    if not match:
        return False
    number = float(match.group(1))
    if number in PLAUSIBLE_VOLTS:
        if category_id in _MAINS_APPLIANCE_CATEGORIES and number < 110:
            return False
        return True
    if category_id in _MAINS_APPLIANCE_CATEGORIES:
        return 110 <= number <= 600 and number == int(number)
    return 12 <= number <= 600 and number == int(number)


def _plausible_size(value: str) -> bool:
    text = (value or "").strip()
    if not text or _junk_spec_value(text):
        return False
    if "x" in text.lower() or '"' in text or re.search(r"\bin\b", text, re.I):
        return True
    match = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return True
    number = float(match.group(1))
    return 8 <= number <= 96


def _plausible_with(value: str) -> bool:
    text = (value or "").strip()
    if not text or _junk_spec_value(text):
        return False
    if re.search(r"with more than", text, re.I):
        return False
    if text.lower() in {"with", "more than"}:
        return False
    return True


_LIGHTING_CATEGORIES = frozenset({"led_lighting", "ceiling_fan"})


def _plausible_wattage(value: str, category_id: str) -> bool:
    match = re.search(r"(\d+(?:\.\d+)?)", value or "")
    if not match:
        return False
    number = float(match.group(1))
    if category_id in _LIGHTING_CATEGORIES:
        return 1 <= number <= 400
    return 10 <= number <= 20000


def _family_from_text(text: str) -> str:
    blob = text or ""
    if re.search(r"(?i)\d+(?:\.\d+)?\s*(?:Watts?\b|W(?![A-Za-z/]))", blob):
        return "wattage"
    if re.search(r"(?i)\d+(?:\.\d+)?\s*(?:VAC|VDC|Volts?\b|V\b)", blob):
        return "voltage"
    if re.search(r"(?i)\d+(?:\.\d+)?\s*(?:Amps?\b|A\b)", blob):
        return "amperage"
    return ""


def uom_fits_label(label: str, uom: str, value: str = "") -> bool:
    """False when a physical unit was parked in the wrong template slot."""
    family = _family_from_text(f"{value} {uom}".strip()) or _uom_family(uom)
    if not family:
        return True
    if label == "Voltage Rating":
        return family == "voltage"
    if label == "Amperage Rating":
        return family == "amperage"
    if label == "Wattage":
        return family == "wattage"
    return True


def _mpn_alnum(mpn: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (mpn or "").upper())


def normalize_color_temperature(value: str, mpn: str = "") -> str:
    """Keep only standard Kelvin / Multi CCT. Drop values that were the MPN."""
    text = (value or "").strip()
    if not text:
        return ""
    lowered = re.sub(r"\s+", " ", text.lower())
    if "multi" in lowered and "cct" in lowered:
        return "Multi CCT"
    match = re.search(r"(\d{4})\s*k\b", text, re.I)
    if not match:
        match = re.fullmatch(r"(\d{4})", text)
    if not match:
        return ""
    kelvin = match.group(1)
    token = f"{kelvin}K"
    compact = _mpn_alnum(mpn)
    if compact and kelvin in compact:
        return ""
    allowed = set(STANDARD_CCTS)
    for values in _load_lov().values():
        allowed.update(values.get("Color Temperature") or [])
    if token not in allowed:
        return ""
    return token


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


def cleanse_attribute(label: str, value: str, uom: str, category_id: str, mpn: str = "") -> tuple[str, str]:
    if not value:
        return value, uom
    if _junk_spec_value(value):
        return "", ""
    if label and value.lower() == label.lower():
        return "", ""
    if mpn and value.lower() == mpn.lower() and label.lower() not in {"model", "alternate_part_number", "sku"}:
        return "", ""
    if label.lower() in {"town_name", "sep", "city", "state", "zip", "postal", "address", "phone", "categories"}:
        return "", ""
    if label == "With" and not _plausible_with(value):
        return "", ""

    if label == "Color Temperature":
        return normalize_color_temperature(value, mpn=mpn), ""
    if not uom_fits_label(label, uom, value):
        return "", ""

    if label in {"Finish", "Color"}:
        if _HEX_COLOR.fullmatch(value.strip()):
            return "", ""
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
        unit = parsed_uom or uom
        if not uom_fits_label(label, unit, parsed_value):
            return "", ""
        if label == "Voltage Rating" and not _plausible_voltage(parsed_value, category_id):
            return "", ""
        if label == "Wattage" and not _plausible_wattage(parsed_value, category_id):
            return "", ""
        if label == "Size" and not _plausible_size(parsed_value):
            return "", ""
        return parsed_value, unit

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
        cleaned_value, cleaned_uom = cleanse_attribute(
            label,
            value,
            uom,
            category_id,
            mpn=row.get("MANUFACTURER_PART_NUMBER") or row.get("Mfg_Part_Num", ""),
        )
        row[f"ATTRIBUTE_VALUE {index}"] = cleaned_value
        row[f"ATTRIBUTE_UOM {index}"] = cleaned_uom

    impute_related_attributes(row)

    if row.get("With") and not _plausible_with(row["With"]):
        row["With"] = ""

    from ingest.csv_io import sanitize_cell

    for field in ("MOBILE_DESC", "SHORT_DESC", "LONG_DESC1", "RETAIL_DESC", "MARKETING_DESCRIPTION"):
        row[field] = re.sub(r"\s+", " ", sanitize_cell(row.get(field, ""))).strip()
    for index in range(1, 21):
        key = f"ITEM_FEATURES_{index}"
        if row.get(key):
            row[key] = sanitize_cell(row[key])

    invoice = re.sub(r"\s+", " ", row.get("INVOICE_DESC", "")).strip()
    # House style: the invoice description is published fully uppercase.
    row["INVOICE_DESC"] = invoice.upper()
