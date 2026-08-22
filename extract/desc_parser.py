import re

from classify.category_router import CategoryTemplate
from extract.evidence import Evidence, EvidenceBundle


def extract_from_part_desc(part_desc: str, mpn: str) -> EvidenceBundle:
    bundle = EvidenceBundle()
    text = part_desc

    patterns = [
        ("Diameter", r'(\d+(?:-\d+/\d+)?|\d+(?:\.\d+)?)\s?(?:\"|in\b)', ""),
        ("Thickness", r'(\.\d+|\d+/\d+)\s?(?:\"|in\b)?', ""),
        ("Arbor Size", r'(\d+/\d|\d+(?:\.\d+)?)\s?(?:\"|in\b)?\s*(?:x|X)\s*(\d+/\d|\d+(?:\.\d+)?)', ""),
        ("Application", r'(Metal Cut Off Disc|Metal Cut-Off Disc|Sanding Belt|Cut Off Disc)', ""),
        ("Pack Quantity", r'(\d+)\s?(?:pc|pk|disc|box)', ""),
    ]

    diameter = re.search(r'(\d+(?:-\d+/\d+)?|\d+(?:\.\d+)?)\s?(?:\"|in)', text, re.I)
    if diameter:
        bundle.set(
            Evidence(
                field="Diameter",
                value=f'{diameter.group(1)}"',
                source_url="input:Part_Desc",
                quote=part_desc[:120],
                extractor="desc_regex",
                confidence=0.7,
            )
        )

    thickness = re.search(r'(\.\d+|\d+/\d+)\s?(?:\"|x|\b)', text, re.I)
    if thickness:
        bundle.set(
            Evidence(
                field="Thickness",
                value=thickness.group(1),
                source_url="input:Part_Desc",
                quote=part_desc[:120],
                extractor="desc_regex",
                confidence=0.65,
            )
        )

    app_match = re.search(r'(Metal Cut Off Disc|Metal Cut-Off Disc|Sanding Belt)', text, re.I)
    if app_match:
        bundle.set(
            Evidence(
                field="Application",
                value=app_match.group(1).title().replace("Off", "Off"),
                source_url="input:Part_Desc",
                quote=part_desc[:120],
                extractor="desc_regex",
                confidence=0.65,
            )
        )

    pack = re.search(r'(\d+)\s?(?:pc|pk|disc|box)', text, re.I)
    if pack:
        bundle.set(
            Evidence(
                field="Pack Quantity",
                value=pack.group(1),
                source_url="input:Part_Desc",
                quote=part_desc[:120],
                extractor="desc_regex",
                confidence=0.6,
            )
        )

    if "Diablo" in text or mpn.startswith("DB"):
        bundle.set(
            Evidence(
                field="Abrasive Material",
                value="Aluminum Oxide",
                source_url="input:Part_Desc",
                quote="Diablo abrasive family",
                extractor="desc_heuristic",
                confidence=0.4,
            )
        )

    return bundle


def build_abrasive_descriptions(row: dict[str, str], template: CategoryTemplate, bundle: EvidenceBundle, mpn: str) -> None:
    brand = row.get("BRAND_NAME", "") or row.get("DIB_Brand", "")
    product = template.product_name
    diameter = bundle.get("Diameter")
    application = bundle.get("Application")
    dia_text = diameter.value if diameter else ""
    app_text = application.value if application else product

    row["MOBILE_DESC"] = f"{brand.replace('®', '')}, {product}, {mpn}, {dia_text}".strip(", ")[:80]
    row["SHORT_DESC"] = f"{brand} {mpn} {app_text}, {dia_text}".strip(", ")
    row["INVOICE_DESC"] = f"{product.upper()} {dia_text}".replace('"', "IN")[:40]
    row["LONG_DESC1"] = f"{brand} {product}, {mpn}, {dia_text}, {app_text}".strip(", ")
    row["RETAIL_DESC"] = f"{product}, {dia_text}".strip(", ")
