import json
import re
from dataclasses import dataclass
from pathlib import Path

from ingest.placeholders import clean_brand

RULES_PATH = Path(__file__).resolve().parent / "mpn_prefix_rules.json"
MANUFACTURER_PATH = Path(__file__).resolve().parent / "manufacturer_map.json"

DESC_PATTERNS: list[tuple[str, str]] = [
    (r"\bGE\b", "GE"),
    (r"Kitchen Aid", "KitchenAid"),
    (r"\bLG\b", "LG"),
    (r"Frigidaire", "Frigidaire"),
    (r"Whirlpool", "Whirlpool"),
    (r"Diablo", "Diablo"),
    (r"\bMilw\b", "Milwaukee"),
    (r"\b3M\b", "3M"),
    (r"Kichler", "Kichler"),
    (r"Philips", "Philips"),
    (r"Leviton", "Leviton"),
    (r"DEWALT", "DEWALT"),
    (r"Satco", "Satco"),
    (r"Hunter", "Hunter"),
    (r"Southwire", "Southwire"),
    (r"Speed Queen", "Speed Queen"),
    (r"\bSQ\b", "Speed Queen"),
    (r"Café|Cafe", "Cafe"),
    (r"Element", "Element"),
]


@dataclass
class Identity:
    brand_key: str
    brand_name: str
    manufacturer_name: str
    domains: list[str]
    confidence: float
    method: str


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def brand_from_mpn_prefix(mpn: str, prefix_rules: dict[str, str]) -> str | None:
    for length in (4, 3, 2):
        prefix = mpn[:length]
        if prefix in prefix_rules:
            return prefix_rules[prefix]
    return None


def brand_from_description(part_desc: str) -> str | None:
    for pattern, brand in DESC_PATTERNS:
        if re.search(pattern, part_desc, re.I):
            return brand
    return None


def resolve_identity(
    mpn: str,
    part_desc: str,
    e1_brand: str,
    dib_brand: str,
) -> Identity:
    prefix_rules = _load_json(RULES_PATH)
    manufacturer_map = _load_json(MANUFACTURER_PATH)

    dib = clean_brand(dib_brand)
    if dib:
        brand_key = dib
        meta = manufacturer_map.get(brand_key, {})
        return Identity(
            brand_key=brand_key,
            brand_name=meta.get("brand_name", dib),
            manufacturer_name=meta.get("manufacturer_name", dib),
            domains=meta.get("domains", []),
            confidence=0.9,
            method="dib_brand",
        )

    e1 = clean_brand(e1_brand)
    if e1:
        brand_key = e1
        meta = manufacturer_map.get(brand_key, {})
        return Identity(
            brand_key=brand_key,
            brand_name=meta.get("brand_name", e1),
            manufacturer_name=meta.get("manufacturer_name", e1),
            domains=meta.get("domains", []),
            confidence=0.85,
            method="e1_brand",
        )

    from_desc = brand_from_description(part_desc)
    if from_desc:
        meta = manufacturer_map.get(from_desc, {})
        return Identity(
            brand_key=from_desc,
            brand_name=meta.get("brand_name", from_desc),
            manufacturer_name=meta.get("manufacturer_name", from_desc),
            domains=meta.get("domains", []),
            confidence=0.75,
            method="part_desc",
        )

    from_prefix = brand_from_mpn_prefix(mpn, prefix_rules)
    if from_prefix:
        meta = manufacturer_map.get(from_prefix, {})
        return Identity(
            brand_key=from_prefix,
            brand_name=meta.get("brand_name", from_prefix),
            manufacturer_name=meta.get("manufacturer_name", from_prefix),
            domains=meta.get("domains", []),
            confidence=0.7,
            method="mpn_prefix",
        )

    return Identity(
        brand_key="",
        brand_name="",
        manufacturer_name="",
        domains=[],
        confidence=0.0,
        method="unknown",
    )
