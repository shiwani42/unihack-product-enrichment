from classify.category_router import CategoryTemplate
from compose.mobile_utils import pad_mobile
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


def build_descriptions(
    row: dict[str, str],
    template: CategoryTemplate,
    bundle: EvidenceBundle,
    mpn: str,
) -> None:
    brand = row.get("BRAND_NAME", "")
    manufacturer = row.get("MANUFACTURER_NAME", "")
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

    invoice_parts = ["DISHWASHER"]
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
    row["INVOICE_DESC"] = " ".join(invoice_parts)[:40]

    if "Whirlpool" in brand:
        mobile = f"Whirlpool, Dishwasher, {series}, {mpn}"
        if mounting:
            mobile += f", {mounting} Mounting"
    elif "FRIGIDAIRE" in brand.upper():
        mobile = f"{manufacturer} FRIGIDAIRE, Dishwasher, {series}, {mpn}"
    else:
        mobile = f"{manufacturer} {brand.replace('®', '')}, Dishwasher, {series}, {mpn}".strip()
    row["MOBILE_DESC"] = pad_mobile(mobile, mpn, brand, manufacturer)

    with_phrase = _with_phrase(with_text.replace("With ", "").replace("with ", ""))
    short_lead = f"{brand} {series} {mpn} Dishwasher".strip()
    if with_phrase and "CleanBoost" in with_phrase:
        short_lead = f"{short_lead} {with_phrase}".strip()
    short_tail = []
    if mounting:
        short_tail.append(f"{mounting} Mounting")
    if cycles:
        short_tail.append(f"{cycles}-Wash Cycle")
    if material:
        short_tail.append(material)
    if color:
        short_tail.append(color)
    row["SHORT_DESC"] = ", ".join([short_lead] + short_tail)

    long_lead = f"{brand} Dishwasher"
    if with_phrase and ("FRIGIDAIRE" in brand.upper() or "CleanBoost" in with_phrase):
        long_lead = f"{long_lead} {with_phrase}"
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
    row["LONG_DESC1"] = ", ".join(part for part in long_parts if part)

    retail_parts = []
    if series:
        retail_parts.append(f"{series} Dishwasher")
    else:
        retail_parts.append("Dishwasher")
    if mounting:
        retail_parts.append(f"{mounting} Mounting")
    if cycles:
        retail_parts.append(f"{cycles}-Wash Cycle")
    if material:
        retail_parts.append(material)
    if color:
        retail_parts.append(color)
    row["RETAIL_DESC"] = ", ".join(retail_parts)

    if with_text:
        row["With"] = with_text if with_text.startswith("With") else f"With {with_text}"
    if bundle.marketing:
        row["MARKETING_DESCRIPTION"] = bundle.marketing
    for index, feature in enumerate(bundle.features[:20], start=1):
        row[f"ITEM_FEATURES_{index}"] = feature
