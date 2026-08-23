"""Stage 8: Digital asset filename conventions for all enriched products.

Filenames follow the Unilog delivery convention (assets are transferred as a
separate package keyed by these names). ``Actual Image (Yes/No)`` is "Yes"
only when a manufacturer image URL was captured. A product page URL or
attribute count is not image evidence.
"""

import re

_VIDEO_URL = re.compile(r"youtube\.com|youtu\.be|vimeo\.com", re.I)


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
    pdfs = []
    if bundle is not None:
        for url in list(getattr(bundle, "ref_urls", []) or []):
            if ".pdf" in (url or "").lower():
                pdfs.append((url or "").lower())
        mfr = (getattr(bundle, "mfr_url", "") or "").lower()
        if ".pdf" in mfr:
            pdfs.append(mfr)
    joined = " ".join(pdfs)
    if any(token in joined for token in ("sds", "msds", "safety-data")):
        row["SDS"] = f"{prefix}_{safe_mpn}_SDS.pdf"
    if any(token in joined for token in ("install", "installation")):
        row["Instruction/Installation Manual"] = f"{prefix}_{safe_mpn}_Installation.pdf"
    if any(token in joined for token in ("owner", "user-manual", "owners-manual")):
        row["Owners/User Manual"] = f"{prefix}_{safe_mpn}_Owners_Manual.pdf"
    if any(token in joined for token in ("warranty",)):
        row["Warranty Information"] = f"{prefix}_{safe_mpn}_Warranty.pdf"
    if any(token in joined for token in ("energy", "energystar")):
        row["Energy Star Guide"] = f"{prefix}_{safe_mpn}_Energy_Guide.pdf"
    videos = []
    if bundle is not None:
        for url in list(getattr(bundle, "ref_urls", []) or []) + list(getattr(bundle, "image_urls", []) or []):
            if _VIDEO_URL.search(url or "") and url not in videos:
                videos.append(url)
    if videos:
        if not (row.get("Video Link") or "").strip():
            row["Video Link"] = videos[0]
        if len(videos) > 1 and not (row.get("Video Link 1") or "").strip():
            row["Video Link 1"] = videos[1]
