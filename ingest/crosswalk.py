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


def apply_product_ids(row: dict[str, str], product_ids: dict[str, str]) -> None:
    if not product_ids:
        return
    mapping = {
        "sku": "PART_NUMBER",
        "productid": "PART_NUMBER",
        "gtin13": "UPC",
        "gtin12": "UPC",
        "upc": "UPC",
        "ean": "EAN",
        "unspsc": "UNSPSC",
    }
    for src, dest in mapping.items():
        value = product_ids.get(src, "").strip()
        if value and not row.get(dest):
            row[dest] = value
