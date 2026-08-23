"""Apply distributor crosswalk IDs when available."""

import json
from pathlib import Path

from app.config import CROSSWALK_PATH


def _load_crosswalk() -> dict[str, dict[str, str]]:
    if not CROSSWALK_PATH.exists():
        return {}
    return json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))


def apply_crosswalk(row: dict[str, str], mpn: str) -> None:
    crosswalk = _load_crosswalk()
    entry = crosswalk.get(mpn.upper()) or crosswalk.get((row.get("Mfg_Part_Num") or "").upper())
    if not entry:
        return
    for field in ("PART_NUMBER", "SKU - MY_PART_NUMBER"):
        value = entry.get(field, "").strip()
        if value:
            row[field] = value


def apply_product_ids(row: dict[str, str], source) -> None:
    """Fill UPC/EAN/GTIN/UNSPSC from structured IDs and leftover spec labels."""
    if not source:
        return
    if hasattr(source, "product_ids"):
        ids = dict(getattr(source, "product_ids", None) or {})
        items = list(getattr(source, "items", None) or [])
    else:
        ids = dict(source)
        items = []
    mapping = {
        "sku": "PART_NUMBER",
        "productid": "PART_NUMBER",
        "gtin13": "GTIN",
        "gtin12": "UPC",
        "gtin8": "EAN",
        "upc": "UPC",
        "ean": "EAN",
        "unspsc": "UNSPSC",
        "countryoforigin": "Country Of Origin",
        "country": "Country Of Origin",
        "gtin": "GTIN",
        "model": "ALTERNATE_PART_NUMBER",
    }
    for item in items:
        key = "".join(ch for ch in (getattr(item, "field", "") or "").lower() if ch.isalnum())
        value = (getattr(item, "value", "") or "").strip()
        if key in mapping and value:
            ids.setdefault(key, value)
    for src, dest in mapping.items():
        value = (ids.get(src) or "").strip()
        if not value or row.get(dest):
            continue
        if dest == "ALTERNATE_PART_NUMBER":
            mpn = (row.get("MANUFACTURER_PART_NUMBER") or row.get("Mfg_Part_Num") or "").strip()
            if mpn and value.lower() == mpn.lower():
                continue
        row[dest] = value
    gtin = (
        ids.get("gtin")
        or ids.get("gtin13")
        or ids.get("gtin12")
        or ids.get("upc")
        or ""
    ).strip()
    if gtin and not row.get("GTIN"):
        row["GTIN"] = gtin
    if len(gtin) == 13 and not row.get("EAN"):
        row["EAN"] = gtin
    if len(gtin) == 12 and not row.get("UPC"):
        row["UPC"] = gtin
