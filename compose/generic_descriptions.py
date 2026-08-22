from classify.category_router import CategoryTemplate
from compose.mobile_utils import pad_mobile
from extract.evidence import EvidenceBundle
from identity.brand_resolver import Identity
from sources.finder import best_mfr_url


def build_generic_descriptions(
    row: dict[str, str],
    template: CategoryTemplate,
    bundle: EvidenceBundle,
    mpn: str,
    identity: Identity,
) -> None:
    brand = row.get("BRAND_NAME") or identity.brand_name or ""
    manufacturer = row.get("MANUFACTURER_NAME") or identity.manufacturer_name or row.get("Part_Manuf", "")
    product = row.get("Product Name") or template.product_name
    part_desc = row.get("Part_Desc", "")

    product_type = bundle.get("Product Type")
    size = bundle.get("Size") or bundle.get("Length") or bundle.get("Width") or bundle.get("Blade Span")
    finish = bundle.get("Finish") or bundle.get("Color")

    type_text = product_type.value if product_type else product
    size_text = size.value if size else ""
    finish_text = finish.value if finish else ""

    mobile_core = ", ".join(
        part for part in [manufacturer, brand.replace("®", "").replace("™", ""), type_text, mpn, size_text, finish_text] if part
    )
    row["MOBILE_DESC"] = pad_mobile(mobile_core, mpn, brand, manufacturer)

    short_parts = [part for part in [brand, mpn, type_text, size_text, finish_text] if part]
    row["SHORT_DESC"] = ", ".join(short_parts)

    row["INVOICE_DESC"] = " ".join(part for part in [type_text.upper(), size_text.replace('"', "IN")] if part)[:40]

    long_parts = [part for part in [brand, type_text, mpn, size_text, finish_text] if part]
    if part_desc and part_desc not in row["SHORT_DESC"]:
        long_parts.append(part_desc[:120])
    row["LONG_DESC1"] = ", ".join(long_parts)

    retail_parts = [part for part in [type_text, size_text, finish_text] if part]
    row["RETAIL_DESC"] = ", ".join(retail_parts) if retail_parts else type_text

    if identity.domains and not row.get("MFR URL"):
        row["MFR URL"] = best_mfr_url(mpn, identity.domains)
