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


def apply_asset_fields(row: dict[str, str], mpn: str) -> None:
    prefix = brand_asset_prefix(row.get("BRAND_NAME", "PRODUCT"))
    row["Product Image"] = f"{prefix}_{mpn}.jpg"
    for index in range(1, 5):
        row[f"Alternate Image {index}"] = f"{prefix}_{mpn}_{index}.jpg"
    row["Specification Sheet"] = f"{prefix}_{mpn}_Specification_Sheet.pdf"
    row["Actual Image (Yes/No)"] = "Yes"
