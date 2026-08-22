"""Delivery-standard description styles, keyed by identity cluster.

The default style is the Unilog mobile/short/long convention. Cluster rows
override only what that family actually writes differently — adding a brand
is a JSON row, not a Python branch. There are no per-SKU keys.

``mobile_lead: "auto"``: if the manufacturer legal name already contains the
brand token, lead with the brand; otherwise ``{manufacturer} {brand_plain}``.
That is an identity fact, not a brand whitelist.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

STYLES_PATH = Path(__file__).resolve().parent / "description_styles.json"

DEFAULT_STYLE = {
    "mobile_lead": "auto",
    "mobile_fill": ["mounting"],
    "short_promote_with": True,
    "long_promote_with": True,
    "title_with": "single",
}


def brand_plain(brand: str) -> str:
    return brand.replace("®", "").replace("™", "").strip()


def manufacturer_contains_brand(manufacturer: str, brand: str) -> bool:
    token = brand_plain(brand)
    if not manufacturer or not token:
        return False
    return bool(re.search(rf"\b{re.escape(token)}\b", manufacturer, re.I))


@lru_cache(maxsize=1)
def _load_styles() -> dict:
    if not STYLES_PATH.exists():
        return {"default": DEFAULT_STYLE, "clusters": {}}
    try:
        payload = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"default": DEFAULT_STYLE, "clusters": {}}
    if not isinstance(payload, dict):
        return {"default": DEFAULT_STYLE, "clusters": {}}
    return payload


def clear_style_cache() -> None:
    _load_styles.cache_clear()


def resolve_style(brand_key: str = "", brand_name: str = "") -> dict:
    payload = _load_styles()
    style = dict(DEFAULT_STYLE)
    style.update(payload.get("default") or {})
    clusters = payload.get("clusters") or {}
    for candidate in (brand_key, brand_plain(brand_name)):
        if not candidate:
            continue
        for key, override in clusters.items():
            if key.lower() == candidate.lower() and isinstance(override, dict):
                style.update(override)
                return style
    return style


def mobile_lead(style: dict, manufacturer: str, brand: str) -> str:
    template = (style.get("mobile_lead") or "auto").strip()
    plain = brand_plain(brand)
    if template == "auto":
        if manufacturer_contains_brand(manufacturer, plain):
            return plain
        return " ".join(part for part in (manufacturer, plain) if part)
    return template.format(
        manufacturer=manufacturer,
        brand_plain=plain,
        brand=brand,
    ).strip()
