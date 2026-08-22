"""Stage 8: Digital asset filename conventions for all enriched products.

Filenames follow the Unilog delivery convention (assets are transferred as a
separate package keyed by these names). ``Actual Image (Yes/No)`` is "Yes"
only when a manufacturer image URL was captured. A product page URL or
attribute count is not image evidence.
"""

import re


def brand_asset_prefix(brand_name: str) -> str:
    cleaned = brand_name.replace("®", "").replace("™", "").strip()
    if cleaned.lower() == "whirlpool":
        return "Whirlpool"
    if cleaned.upper() == "FRIGIDAIRE":
        return "FRIGIDAIRE"
    parts = re.findall(r"[A-Za-z0-9]+", cleaned)
    if not parts:
        return "PRODUCT"
    if len(parts) == 1:
        token = parts[0]
        if token.isupper():
            return token
        return token[:1].upper() + token[1:]
    return "_".join(part[:1].upper() + part[1:] for part in parts)


def has_image_evidence(bundle) -> bool:
    if bundle is None:
        return False
    return any(str(url).strip() for url in getattr(bundle, "image_urls", []) or [])


def apply_asset_fields(row: dict[str, str], mpn: str, bundle=None) -> None:
    prefix = brand_asset_prefix(row.get("BRAND_NAME", "") or row.get("MANUFACTURER_NAME", "PRODUCT"))
    safe_mpn = re.sub(r"[^\w\-]+", "_", mpn)
    row["Product Image"] = f"{prefix}_{safe_mpn}.jpg"
    for index in range(1, 5):
        row[f"Alternate Image {index}"] = f"{prefix}_{safe_mpn}_{index}.jpg"
    row["Specification Sheet"] = f"{prefix}_{safe_mpn}_Specification_Sheet.pdf"
    row["Actual Image (Yes/No)"] = "Yes" if has_image_evidence(bundle) else "No"
