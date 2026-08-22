"""Unit parsing and normalization for attribute values."""

import re

DIMENSION_RE = re.compile(
    r"(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s*(?:\"|in\b|inch|inches)?",
    re.I,
)
FRACTION_RE = re.compile(r"(\d+)-(\d+/\d+)")


def parse_fraction(token: str) -> str:
    match = FRACTION_RE.match(token.strip())
    if not match:
        return token.strip()
    whole, frac = match.groups()
    return f"{whole}-{frac}"


def split_value_uom(raw: str, expected_uom: str = "") -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        return "", ""

    # Explicit non-imperial units are always preserved verbatim; a bare number
    # is the only case where the template's expected UOM may be assumed.
    metric = re.match(r"^(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s+(mm|cm|m|ft|feet|foot|')$", text, re.I)
    if metric:
        value = parse_fraction(metric.group(1))
        unit = metric.group(2).lower()
        uom_map = {"feet": "ft", "foot": "ft"}
        return value, uom_map.get(unit, unit)
    attached = re.match(r"^(\d+(?:\.\d+)?)(')$", text)
    if attached:
        return attached.group(1), "ft"

    volt = re.match(r"^(\d{2,3})\s*(V|VAC|Volts?)$", text, re.I)
    if volt:
        return volt.group(1), expected_uom or "V"

    amp = re.match(r"^(\d+(?:\.\d+)?)\s*(A|Amps?)$", text, re.I)
    if amp:
        return amp.group(1), expected_uom or "A"

    watt = re.match(r"^(\d+(?:\.\d+)?)\s*(W|Watts?)$", text, re.I)
    if watt:
        return watt.group(1), expected_uom or "W"

    inch = re.match(r'^(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s*(?:"|in|inch|inches)$', text, re.I)
    if inch:
        return parse_fraction(inch.group(1)), expected_uom or "in"

    bare_number = re.match(r"^(\d+(?:-\d+/\d+)?(?:\.\d+)?)$", text)
    if bare_number and expected_uom:
        # Bare numbers adopt the template's expected UOM (no conversion happens).
        return parse_fraction(bare_number.group(1)), expected_uom

    dba = re.match(r"^(\d+)\s*(dBA|dba)$", text, re.I)
    if dba:
        return dba.group(1), expected_uom or "dBA"

    if expected_uom:
        return text, expected_uom
    return text, ""


def normalize_dimension_list(text: str) -> str:
    parts = re.split(r"\s*[xX×]\s*", text)
    normalized = []
    for part in parts:
        value, uom = split_value_uom(part.strip(), "in")
        if value:
            normalized.append(f'{value}"' if uom == "in" and '"' not in value else value)
    return " x ".join(normalized)
