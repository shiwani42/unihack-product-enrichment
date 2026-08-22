import json
import re
from dataclasses import dataclass
from pathlib import Path

from ingest.placeholders import clean_brand

RULES_PATH = Path(__file__).resolve().parent / "mpn_prefix_rules.json"
MANUFACTURER_PATH = Path(__file__).resolve().parent / "manufacturer_map.json"
ALIASES_PATH = Path(__file__).resolve().parent / "brand_aliases.json"
HINTS_PATH = Path(__file__).resolve().parent / "manufacturer_hints.json"

COOP_CODES = {"APPDE", "UNILOG", "COOP"}


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


def _brand_names(manufacturer_map: dict) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    for key, meta in manufacturer_map.items():
        names.append((key, key))
        brand_name = meta.get("brand_name", "")
        cleaned = re.sub(r"[®™]", "", brand_name).strip()
        if cleaned and cleaned.lower() != key.lower():
            names.append((cleaned, key))
    return sorted(names, key=lambda item: len(item[0]), reverse=True)


def brand_from_manufacturer_map(text: str, manufacturer_map: dict) -> str | None:
    lowered = text.lower()
    for name, key in _brand_names(manufacturer_map):
        if re.search(rf"\b{re.escape(name.lower())}\b", lowered):
            return key
    return None


def brand_from_aliases(text: str, aliases: dict[str, str]) -> str | None:
    for alias, brand_key in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text, re.I):
            return brand_key
    return None


def brand_from_description(part_desc: str, manufacturer_map: dict | None = None) -> str | None:
    manufacturer_map = manufacturer_map or _load_json(MANUFACTURER_PATH)
    aliases = _load_json(ALIASES_PATH) if ALIASES_PATH.exists() else {}
    from_alias = brand_from_aliases(part_desc, aliases)
    if from_alias:
        return from_alias
    return brand_from_manufacturer_map(part_desc, manufacturer_map)


def brand_from_part_manuf(part_manuf: str, manufacturer_map: dict) -> str | None:
    if re.search(r"\bAPPDE\b|Appliance Dealers Cooperative", part_manuf, re.I):
        return None
    token = clean_brand(part_manuf)
    if not token or token.upper() in COOP_CODES:
        hints = _load_json(HINTS_PATH) if HINTS_PATH.exists() else {}
        for hint, brand_key in sorted(hints.items(), key=lambda item: len(item[0]), reverse=True):
            if hint.lower() in part_manuf.lower() and brand_key in manufacturer_map:
                return brand_key
        return None
    if token in manufacturer_map:
        return token
    hints = _load_json(HINTS_PATH) if HINTS_PATH.exists() else {}
    for hint, brand_key in sorted(hints.items(), key=lambda item: len(item[0]), reverse=True):
        if hint.lower() in part_manuf.lower() and brand_key in manufacturer_map:
            return brand_key
    return brand_from_manufacturer_map(part_manuf, manufacturer_map)


def brand_from_mpn_prefix(mpn: str, prefix_rules: dict[str, str], part_desc: str, manufacturer_map: dict) -> str | None:
    desc_brand = brand_from_description(part_desc, manufacturer_map)
    for length in (4, 3, 2):
        prefix = mpn[:length]
        if prefix not in prefix_rules:
            continue
        candidate = prefix_rules[prefix]
        if desc_brand and desc_brand != candidate:
            if re.search(r"gilmour|makita|amana", part_desc, re.I) and candidate == "Hunter":
                continue
        return candidate
    return None


def resolve_identity(
    mpn: str,
    part_desc: str,
    e1_brand: str,
    dib_brand: str,
    part_manuf: str = "",
    unilog_brand: str = "",
) -> Identity:
    prefix_rules = _load_json(RULES_PATH)
    manufacturer_map = _load_json(MANUFACTURER_PATH)

    dib = clean_brand(dib_brand)
    if dib:
        brand_key = dib if dib in manufacturer_map else brand_from_manufacturer_map(dib, manufacturer_map) or dib
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
        brand_key = e1 if e1 in manufacturer_map else brand_from_manufacturer_map(e1, manufacturer_map) or e1
        meta = manufacturer_map.get(brand_key, {})
        return Identity(
            brand_key=brand_key,
            brand_name=meta.get("brand_name", e1),
            manufacturer_name=meta.get("manufacturer_name", e1),
            domains=meta.get("domains", []),
            confidence=0.85,
            method="e1_brand",
        )

    unilog = clean_brand(unilog_brand)
    if unilog:
        brand_key = unilog if unilog in manufacturer_map else brand_from_manufacturer_map(unilog, manufacturer_map) or unilog
        meta = manufacturer_map.get(brand_key, {})
        return Identity(
            brand_key=brand_key,
            brand_name=meta.get("brand_name", unilog),
            manufacturer_name=meta.get("manufacturer_name", unilog),
            domains=meta.get("domains", []),
            confidence=0.82,
            method="unilog_brand",
        )

    from_manuf = brand_from_part_manuf(part_manuf, manufacturer_map)
    if from_manuf:
        meta = manufacturer_map.get(from_manuf, {})
        return Identity(
            brand_key=from_manuf,
            brand_name=meta.get("brand_name", from_manuf),
            manufacturer_name=meta.get("manufacturer_name", from_manuf),
            domains=meta.get("domains", []),
            confidence=0.8,
            method="part_manuf",
        )

    from_desc = brand_from_description(part_desc, manufacturer_map)
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

    from_prefix = brand_from_mpn_prefix(mpn, prefix_rules, part_desc, manufacturer_map)
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
