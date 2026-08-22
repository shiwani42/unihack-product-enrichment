from classify.category_router import CategoryTemplate
from compose.mobile_utils import pad_mobile
from compose.style_table import mobile_lead, resolve_style
from extract.evidence import EvidenceBundle


def _attr(bundle: EvidenceBundle, label: str) -> tuple[str, str]:
    evidence = bundle.get(label)
    if not evidence:
        return "", ""
    return evidence.value, evidence.uom


def _with_phrase(with_text: str) -> str:
    if not with_text:
        return ""
    return with_text if with_text.lower().startswith("with ") else f"With {with_text}"


def _title_with(with_phrase: str, style: dict) -> str:
    """Put a With-feature in the title only when it is a single qualifier.

    Delivery titles stay tight: "With CleanBoost™" belongs in SHORT/LONG;
    "With A, B, C" stays in the With column only.
    """
    if not with_phrase:
        return ""
    mode = (style.get("title_with") or "single").lower()
    if mode == "never":
        return ""
    if mode == "always":
        return with_phrase
    body = with_phrase[5:].strip() if with_phrase.lower().startswith("with ") else with_phrase
    if "," in body:
        return ""
    return with_phrase


def _join(parts: list[str]) -> str:
    return ", ".join(part for part in parts if part)


def build_descriptions(
    row: dict[str, str],
    template: CategoryTemplate,
    bundle: EvidenceBundle,
    mpn: str,
) -> None:
    brand = row.get("BRAND_NAME", "")
    manufacturer = row.get("MANUFACTURER_NAME", "")
    style = resolve_style(brand_name=brand)
    product = row.get("Product Name") or template.product_name or "Dishwasher"
    rules = template.description_rules or {}
    mobile_min = int(rules.get("mobile_min_chars", 60))
    mobile_max = int(rules.get("mobile_max_chars", 80))

    series, _ = _attr(bundle, "Series")
    mounting, _ = _attr(bundle, "Mounting Type")
    volt, volt_uom = _attr(bundle, "Voltage Rating")
    amp, amp_uom = _attr(bundle, "Amperage Rating")
    sound, sound_uom = _attr(bundle, "Sound Level")
    material, _ = _attr(bundle, "Material")
    color, _ = _attr(bundle, "Color")
    cycles, _ = _attr(bundle, "Number of Wash Cycles")
    depth, depth_uom = _attr(bundle, "Depth With Door Open")
    size, _ = _attr(bundle, "Size")
    min_height, min_uom = _attr(bundle, "Minimum Height")
    max_height, _ = _attr(bundle, "Maximum Height")
    additional, _ = _attr(bundle, "Additional Information")
    with_evidence = bundle.get("With")
    with_text = with_evidence.value if with_evidence else ""

    mount_abbr = ""
    if mounting:
        if mounting.lower() == "leg":
            mount_abbr = "LEG"
        elif "built" in mounting.lower():
            mount_abbr = "BLTLN"

    invoice_parts = [product.upper()]
    if mount_abbr:
        invoice_parts.append(mount_abbr)
    if cycles:
        invoice_parts.append(cycles)
    if material:
        invoice_parts.append("SST")
    if color and color == material:
        invoice_parts.append("SST")
    if volt:
        invoice_parts.append(f"{volt}V")
    if amp:
        invoice_parts.append(f"{amp}A")
    if sound:
        invoice_parts.append(f"{sound}{sound_uom or 'DBA'}".upper())
    if depth and mount_abbr == "LEG":
        invoice_parts = [part for part in invoice_parts if not part.endswith("DBA")]
        depth_token = depth.replace(" ", "").upper()
        if not depth_token.endswith("IN"):
            depth_token = f"{depth_token}IN"
        invoice_parts.append(depth_token)
    elif depth and not sound:
        depth_token = depth.replace(" ", "").upper()
        if not depth_token.endswith("IN"):
            depth_token = f"{depth_token}IN"
        invoice_parts.append(depth_token)
    row["INVOICE_DESC"] = " ".join(invoice_parts).upper()[:40]

    lead = mobile_lead(style, manufacturer, brand)
    mobile_parts = [lead, product, series, mpn]
    fill = style.get("mobile_fill") or []
    if "mounting" in fill and mounting and len(_join(mobile_parts)) < mobile_min:
        mobile_parts.append(f"{mounting} Mounting")
    row["MOBILE_DESC"] = pad_mobile(_join(mobile_parts), mpn, brand, manufacturer, minimum=mobile_min)[:mobile_max]

    with_phrase = _with_phrase(with_text.replace("With ", "").replace("with ", ""))
    title_with = _title_with(with_phrase, style)
    short_lead = f"{brand} {series} {mpn} {product}".strip()
    if title_with and style.get("short_promote_with"):
        short_lead = f"{short_lead} {title_with}".strip()
    short_tail = []
    if mounting:
        short_tail.append(f"{mounting} Mounting")
    if cycles:
        short_tail.append(f"{cycles}-Wash Cycle")
    if material:
        short_tail.append(material)
    if color:
        short_tail.append(color)
    row["SHORT_DESC"] = _join([short_lead] + short_tail)

    long_lead = f"{brand} {product}"
    if title_with and style.get("long_promote_with"):
        long_lead = f"{long_lead} {title_with}"
    long_parts = [long_lead]
    if series:
        long_parts.append(series)
    if cycles:
        long_parts.append(f"{cycles} Wash Cycles")
    if volt:
        long_parts.append(f"{volt} {volt_uom or 'V'}")
    if amp:
        long_parts.append(f"{amp} {amp_uom or 'A'}")
    if mounting:
        long_parts.append(f"{mounting} Mounting")
    if size:
        long_parts.append(size)
    if depth:
        long_parts.append(f"{depth} {depth_uom or 'in'} Depth With Door Open")
    if min_height:
        if "Rack" in min_height:
            long_parts.append(f"{min_height} Minimum Height")
        else:
            long_parts.append(f"{min_height} {min_uom or 'in'} Minimum Height")
    if max_height:
        long_parts.append(f"{max_height} Maximum Height")
    if sound:
        long_parts.append(f"{sound} {sound_uom or 'dBA'} Sound Level")
    if material:
        long_parts.append(material)
    if color:
        long_parts.append(color)
    if additional:
        long_parts.append(f"Additional Information: {additional}")
    row["LONG_DESC1"] = _join(long_parts)

    retail_parts = []
    if series:
        retail_parts.append(f"{series} {product}")
    else:
        retail_parts.append(product)
    if mounting:
        retail_parts.append(f"{mounting} Mounting")
    if cycles:
        retail_parts.append(f"{cycles}-Wash Cycle")
    if material:
        retail_parts.append(material)
    if color:
        retail_parts.append(color)
    row["RETAIL_DESC"] = _join(retail_parts)

    if with_text:
        row["With"] = with_text if with_text.startswith("With") else f"With {with_text}"
    if bundle.marketing:
        row["MARKETING_DESCRIPTION"] = bundle.marketing
    for index, feature in enumerate(bundle.features[:20], start=1):
        row[f"ITEM_FEATURES_{index}"] = feature
