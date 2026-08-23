"""Stage 1: Input analysis — normalize messy distributor rows before enrichment."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ingest.placeholders import clean_brand

ABBREV_PATH = Path(__file__).resolve().parent / "abbreviations.json"
MPN_SUFFIX_RE = re.compile(r"(?i)(-UPC|-JR|-PKG|-BX|-BOX|-EA|-PK|-PACK|-BULK)$")
VENDOR_PREFIX_RE = re.compile(r"^([A-Z0-9]{2,6})-(.+)$")


@dataclass
class AnalyzedInput:
    raw_mpn: str
    raw_desc: str
    normalized_mpn: str
    search_mpn: str
    expanded_desc: str
    clean_desc: str
    embedded_mpn: str
    abbreviations_found: list[str] = field(default_factory=list)
    empty_fields: list[str] = field(default_factory=list)
    quality_score: float = 0.0


def _load_abbreviations() -> dict[str, str]:
    if not ABBREV_PATH.exists():
        return {}
    return json.loads(ABBREV_PATH.read_text(encoding="utf-8"))


def normalize_mpn(mpn: str) -> str:
    token = (mpn or "").strip().upper()
    token = MPN_SUFFIX_RE.sub("", token)
    token = re.sub(r"\s+", "", token)
    return token


def search_mpn(mpn: str) -> str:
    normalized = normalize_mpn(mpn)
    if normalized.endswith("Z") and len(normalized) > 4:
        return normalized[:-1]
    return normalized


def strip_vendor_prefix(mpn: str) -> str:
    """Drop a letter distributor prefix. Never strip Milwaukee-style ``49-94-0013``."""
    return catalog_id(mpn)


def catalog_id(mpn: str, brand_key: str = "") -> str:
    """Manufacturer catalog ID when the input MPN is a distributor wrapper.

    ``3MABR-7100075678`` is Jam's prefix plus 3M's 10-digit stock number.
    ``49-94-0013`` is Milwaukee's own ID and must stay intact.
    """
    normalized = normalize_mpn(mpn)
    match = VENDOR_PREFIX_RE.match(normalized)
    if not match:
        return normalized
    prefix, rest = match.group(1), match.group(2)
    if not re.search(r"[A-Z]", prefix):
        return normalized
    if rest.isdigit() and len(rest) >= 8:
        return rest
    compact = re.sub(r"[^A-Z0-9]", "", (brand_key or "").upper())
    if compact and prefix.startswith(compact) and len(rest) >= 6:
        return rest
    return normalized


def catalog_search_mpn(mpn: str, brand_key: str = "") -> str:
    """Token to type into manufacturer search and web search."""
    raw = normalize_mpn(mpn)
    cat = catalog_id(raw, brand_key)
    if cat != raw:
        return cat
    return search_mpn(raw)


def _clean_desc_text(desc: str) -> str:
    text = (desc or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("''", '"').replace('""', '"')
    return text


def expand_abbreviations(text: str, abbreviations: dict[str, str]) -> tuple[str, list[str]]:
    found: list[str] = []
    expanded = text
    for abbr, full in sorted(abbreviations.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = rf"\b{re.escape(abbr)}\b"
        if re.search(pattern, expanded, re.I):
            found.append(abbr)
            expanded = re.sub(pattern, full, expanded, flags=re.I)
    return expanded, found


def extract_embedded_mpn(desc: str, raw_mpn: str) -> str:
    cleaned = _clean_desc_text(desc)
    normalized = normalize_mpn(raw_mpn)
    match = re.match(rf"^({re.escape(normalized)})\b", cleaned, re.I)
    if match:
        return normalized
    token_match = re.search(r"\b([A-Z0-9][A-Z0-9\-/]{3,})\b", cleaned)
    if token_match:
        candidate = normalize_mpn(token_match.group(1))
        if candidate != normalized and len(candidate) >= 4:
            return candidate
    return ""


def analyze_input_row(row: dict[str, str]) -> AnalyzedInput:
    raw_mpn = row.get("Mfg_Part_Num", "").strip()
    raw_desc = row.get("Part_Desc", "").strip()
    abbreviations = _load_abbreviations()

    normalized_mpn = normalize_mpn(raw_mpn)
    clean_desc = _clean_desc_text(raw_desc)
    expanded_desc, found = expand_abbreviations(clean_desc, abbreviations)
    embedded_mpn = extract_embedded_mpn(clean_desc, raw_mpn)

    empty_fields = []
    for col in ("E1_Brand", "Unilog_Brand", "DIB_Brand"):
        if not clean_brand(row.get(col, "")):
            empty_fields.append(col)
    if not row.get("Part_Manuf", "").strip():
        empty_fields.append("Part_Manuf")

    filled = 6 - len(empty_fields)
    quality_score = round(filled / 6, 2)

    return AnalyzedInput(
        raw_mpn=raw_mpn,
        raw_desc=raw_desc,
        normalized_mpn=normalized_mpn,
        search_mpn=search_mpn(raw_mpn),
        expanded_desc=expanded_desc,
        clean_desc=clean_desc,
        embedded_mpn=embedded_mpn,
        abbreviations_found=found,
        empty_fields=empty_fields,
        quality_score=quality_score,
    )
