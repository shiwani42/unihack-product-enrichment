DESCRIPTION_FIELDS = (
    ("INVOICE_DESC", "Invoice Description", 40),
    ("MOBILE_DESC", "Mobile Description", 80),
    ("SHORT_DESC", "Short Description", 240),
    ("LONG_DESC1", "Long Description", None),
    ("RETAIL_DESC", "Retail Description", None),
    ("MARKETING_DESCRIPTION", "Marketing Description", None),
)

FEATURE_FIELDS = tuple(f"ITEM_FEATURES_{index}" for index in range(1, 21))

SOURCE_FIELDS = ("MFR URL", "Ref URL 1", "Ref URL 2", "Ref URL 3", "Ref URL 4", "Ref URL 5")

TAXONOMY_FIELDS = ("Dept", "Class", "Fine", "Classpath")

IDENTITY_FIELDS = (
    "Mfg_Part_Num",
    "Part_Desc",
    "MANUFACTURER_NAME",
    "BRAND_NAME",
    "MANUFACTURER_PART_NUMBER",
    "Part_Manuf",
)

ASSET_FIELDS = (
    ("ASSET_ITEM_IMAGE_PRIMARY_FILE_NAME", "Primary Product Image", "image"),
    ("ASSET_ITEM_IMAGE_SECONDARY_1_FILE_NAME", "Secondary Product Image", "image"),
    ("ASSET_ITEM_MANUAL_FILE_NAME", "Owner / User Manual (PDF)", "document"),
    ("ASSET_ITEM_SPEC_FILE_NAME", "Technical Specification Sheet (PDF)", "document"),
    ("ASSET_ITEM_MSDS_FILE_NAME", "MSDS / SDS Sheet (PDF)", "document"),
    ("ASSET_ITEM_WARRANTY_FILE_NAME", "Warranty Documentation (PDF)", "document"),
)

COMMERCIAL_ID_FIELDS = (
    ("PART_NUMBER", "Distributor Part Number"),
    ("SKU - MY_PART_NUMBER", "Distributor SKU"),
    ("UPC", "Universal Product Code (UPC)"),
    ("EAN", "European Article Number (EAN)"),
    ("UNSPSC", "UNSPSC Code"),
    ("With", "Included Accessories / Features"),
)

INPUT_FIELDS = (
    "Mfg_Part_Num",
    "Part_Desc",
    "E1_Brand",
    "Unilog_Brand",
    "DIB_Brand",
    "Part_Manuf",
)

TOTAL_OUTPUT_COLUMNS = 252


def row_preview(row: dict[str, str], report: dict, input_row: dict[str, str] | None = None) -> dict:
    field_sources = report.get("field_sources", {}) if isinstance(report, dict) else {}

    # Category structured attributes (slots 1..50)
    structured_specs = []
    attributes_dict = {}
    for i in range(1, 51):
        label = (row.get(f"ATTRIBUTE_LABEL {i}") or "").strip()
        val = (row.get(f"ATTRIBUTE_VALUE {i}") or "").strip()
        uom = (row.get(f"ATTRIBUTE_UOM {i}") or "").strip()
        if label and val:
            display_val = f"{val} {uom}".strip() if uom else val
            attributes_dict[label] = display_val
            source = field_sources.get(label) or field_sources.get(f"ATTRIBUTE_VALUE {i}") or field_sources.get("MFR URL", "input:Part_Desc")
            structured_specs.append({
                "slot": i,
                "label": label,
                "value": val,
                "uom": uom,
                "display": display_val,
                "source": source,
            })

    # Description fields
    descriptions = []
    descriptions_dict = {}
    for field_key, field_title, max_len in DESCRIPTION_FIELDS:
        val = (row.get(field_key) or "").strip()
        if val:
            descriptions_dict[field_key] = val
            is_valid = True
            if max_len and len(val) > max_len:
                is_valid = False
            if field_key == "MOBILE_DESC" and len(val) < 60:
                is_valid = False
            descriptions.append({
                "key": field_key,
                "title": field_title,
                "value": val,
                "length": len(val),
                "max_len": max_len,
                "min_len": 60 if field_key == "MOBILE_DESC" else None,
                "valid": is_valid,
            })

    # Item features
    features = [row.get(field, "").strip() for field in FEATURE_FIELDS if (row.get(field) or "").strip()]

    # Sources
    sources = {}
    for field in SOURCE_FIELDS:
        url = (row.get(field) or "").strip()
        if url:
            sources[field] = url

    # Digital assets
    assets = []
    for field_key, field_title, asset_type in ASSET_FIELDS:
        val = (row.get(field_key) or "").strip()
        if val:
            assets.append({
                "field": field_key,
                "title": field_title,
                "type": asset_type,
                "filename": val,
            })

    # Commercial IDs
    commercial_ids = []
    for field_key, field_title in COMMERCIAL_ID_FIELDS:
        val = (row.get(field_key) or "").strip()
        if val:
            commercial_ids.append({
                "field": field_key,
                "title": field_title,
                "value": val,
            })

    # All populated fields out of 252
    populated_fields = [
        {"field": k, "value": v}
        for k, v in row.items()
        if (v or "").strip()
    ]

    filled = report.get("filled_fields", len(populated_fields))
    mpn = report.get("mpn", row.get("Mfg_Part_Num", ""))
    confidence_band = report.get("confidence_band", "medium")
    evidence_count = report.get("evidence_count", len(structured_specs))
    issues = report.get("issues", [])
    issue_count = report.get("issue_count", len(issues))
    category_id = report.get("category_id", "")

    return {
        "mpn": mpn,
        "confidence_band": confidence_band,
        "evidence_count": evidence_count,
        "filled_fields": filled,
        "completeness_pct": round(filled / TOTAL_OUTPUT_COLUMNS * 100, 1),
        "issue_count": issue_count,
        "issues": issues,
        "category_id": category_id,
        "input": {field: (input_row or row).get(field, "") for field in INPUT_FIELDS},
        "identity": {field: row.get(field, "") for field in IDENTITY_FIELDS},
        "taxonomy": {field: row.get(field, "") for field in TAXONOMY_FIELDS if (row.get(field) or "").strip()},
        "attributes": attributes_dict,
        "specs": structured_specs,
        "descriptions": descriptions_dict,
        "descriptions_list": descriptions,
        "features": features,
        "sources": sources,
        "assets": assets,
        "commercial_ids": commercial_ids,
        "populated_fields": populated_fields,
        "storefront_title": row.get("SHORT_DESC") or row.get("RETAIL_DESC") or mpn,
        "storefront_summary": row.get("MARKETING_DESCRIPTION") or row.get("MOBILE_DESC") or "",
        "long_desc": row.get("LONG_DESC1") or "",
    }
