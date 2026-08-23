import re

from classify.category_router import CategoryTemplate
from compose.mobile_utils import pad_mobile
from extract.evidence import Evidence, EvidenceBundle
from sources.finder import best_mfr_url


def extract_from_part_desc(part_desc: str, mpn: str, brand_key: str = "", domains: list | None = None) -> EvidenceBundle:
    bundle = EvidenceBundle()
    text = part_desc
    source = "input:Part_Desc"

    def add(field: str, value: str, confidence: float = 0.65) -> None:
        if not value:
            return
        bundle.set(
            Evidence(
                field=field,
                value=value,
                source_url=source,
                quote=part_desc[:120],
                extractor="desc_regex",
                confidence=confidence,
            )
        )

    diameter = re.search(r'(\d+(?:-\d+/\d+)?|\d+(?:\.\d+)?)\s?(?:"|in\b)', text, re.I)
    if diameter:
        add("Diameter", f'{diameter.group(1)}"', 0.7)

    thickness = re.search(r'(\.\d+|\d+/\d+)\s?(?:"|x|\b)', text, re.I)
    if thickness and not re.search(r"P\d{2,3}\b", text):
        add("Thickness", thickness.group(1), 0.65)

    grit = re.search(r"\bP(\d{2,3})\b", text, re.I)
    grit_plain = re.search(r"\b(\d{2,3})\s*grit\b", text, re.I)
    if grit:
        add("Grit", f"P{grit.group(1)}", 0.7)
        add("Additional Information", f"P{grit.group(1)} Grit", 0.7)
    elif grit_plain:
        add("Grit", grit_plain.group(1), 0.7)
        add("Additional Information", f"{grit_plain.group(1)} Grit", 0.65)

    dims = re.search(r"(\d+(?:\.\d+)?)\s?[xX]\s?(\d+(?:\.\d+)?)", text)
    if dims and not diameter:
        add("Diameter", f"{dims.group(1)}x{dims.group(2)}", 0.6)

    app_match = re.search(
        r"(Metal Cut Off Disc|Metal Cut-Off Disc|Sanding Belt|Sanding Sponge|Stikit Film|Abranet|Sanding Disc|HIOLIT|Screw Setter)",
        text,
        re.I,
    )
    if app_match:
        app_val = app_match.group(1).title()
        if app_val.upper() == "HIOLIT":
            app_val = "Sanding Disc"
        add("Application", app_val, 0.65)
        add("Product Type", app_val, 0.6)

    type_match = re.search(
        r"(Sanding Sponge|Sanding Belt|Sanding Disc|Screw Setter|Cut[- ]?Off Disc|Grinding Wheel)",
        text,
        re.I,
    )
    if type_match and not bundle.get("Product Type"):
        add("Product Type", type_match.group(1).title(), 0.6)

    pack = re.search(r"(\d+)\s?(?:pc|pk|disc|box)\b", text, re.I)
    if pack:
        add("Pack Quantity", pack.group(1), 0.6)

    material = re.search(
        r"(Aluminum Oxide|Silicon Carbide|Zirconia Alumina|Ceramic Alumina|Ceramic)\b",
        text,
        re.I,
    )
    if material:
        add("Abrasive Material", material.group(1).title(), 0.6)

    if domains:
        url = best_mfr_url(mpn, domains)
        if url:
            bundle.mfr_url = url

    return bundle


def build_abrasive_descriptions(
    row: dict[str, str],
    template: CategoryTemplate,
    bundle: EvidenceBundle,
    mpn: str,
) -> None:
    brand = row.get("BRAND_NAME", "") or row.get("MANUFACTURER_NAME", "")
    manufacturer = row.get("MANUFACTURER_NAME", "")
    product = template.product_name
    diameter = bundle.get("Diameter")
    application = bundle.get("Application")
    dia_text = diameter.value if diameter else ""
    app_text = application.value if application else product
    part_desc = row.get("Part_Desc", "")

    mobile_core = ", ".join(
        part for part in [manufacturer, brand.replace("®", "").replace("™", ""), product, mpn, dia_text, app_text] if part
    )
    row["MOBILE_DESC"] = pad_mobile(mobile_core, mpn, brand, manufacturer)
    row["SHORT_DESC"] = ", ".join(part for part in [brand, mpn, app_text, dia_text] if part)
    row["INVOICE_DESC"] = f"{product.upper()} {dia_text}".replace('"', "IN").strip()[:40]
    row["LONG_DESC1"] = ", ".join(part for part in [brand, product, mpn, dia_text, app_text, part_desc[:80]] if part)
    row["RETAIL_DESC"] = ", ".join(part for part in [product, dia_text, app_text] if part)
