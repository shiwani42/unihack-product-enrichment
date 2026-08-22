"""Unit parsing and normalization for attribute values."""

import json
import re
from functools import lru_cache
from pathlib import Path

DIMENSION_RE = re.compile(
    r"(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s*(?:\"|in\b|inch|inches)?",
    re.I,
)
FRACTION_RE = re.compile(r"(\d+)-(\d+/\d+)")
FRACTION_TABLE = Path(__file__).resolve().parents[1] / "data" / "reference" / "fraction_inch.json"
INCH_UOMS = frozenset({"in", "inch", "inches", '"'})


@lru_cache(maxsize=1)
def _fraction_table() -> dict[str, str]:
    if not FRACTION_TABLE.exists():
        return {}
    try:
        payload = json.loads(FRACTION_TABLE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    raw = payload.get("decimal_to_fraction") or {}
    return {str(k): str(v) for k, v in raw.items()}


def _decimal_key(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def decimal_to_fraction(token: str) -> str:
    """Map 0.25 -> 1/4 and 50.25 -> 50-1/4 when the fraction table is present."""
    text = (token or "").strip()
    if not text or "/" in text:
        return parse_fraction(text)
    try:
        value = float(text)
    except ValueError:
        return text
    table = _fraction_table()
    if not table:
        return text
    direct = table.get(_decimal_key(value))
    if direct:
        return direct
    whole = int(value)
    remainder = value - whole
    if whole and remainder > 1e-9:
        part = table.get(_decimal_key(remainder))
        if part:
            return f"{whole}-{part}"
    return text


def parse_fraction(token: str) -> str:
    """Keep already-fractional inch forms (50-1/4). Do not convert metric decimals."""
    text = (token or "").strip()
    match = FRACTION_RE.match(text)
    if match:
        whole, frac = match.groups()
        return f"{whole}-{frac}"
    return text


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
        raw_value = inch.group(1)
        value = decimal_to_fraction(raw_value) if "." in raw_value else parse_fraction(raw_value)
        return value, expected_uom or "in"

    bare_number = re.match(r"^(\d+(?:-\d+/\d+)?(?:\.\d+)?)$", text)
    if bare_number and expected_uom:
        value = parse_fraction(bare_number.group(1))
        if expected_uom.lower() in INCH_UOMS:
            value = decimal_to_fraction(value)
        return value, expected_uom

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
