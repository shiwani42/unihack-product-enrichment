from classify.category_router import CategoryTemplate
from extract.evidence import EvidenceBundle


def _attr(bundle: EvidenceBundle, label: str) -> tuple[str, str]:
    evidence = bundle.get(label)
    if not evidence:
        return "", ""
    return evidence.value, evidence.uom


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
    with_value = bundle.get("With")
    with_text = with_value.value if with_value else ""

    mount_abbr = ""
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
    if color and color != material:
        invoice_parts.append("SST")
    if volt:
        invoice_parts.append(f"{volt}V")
    if amp:
        invoice_parts.append(f"{amp}A")
    if depth:
        invoice_parts.append(f"{depth.replace(' ', '')}{depth_uom or 'IN'}".upper())
    elif sound:
        invoice_parts.append(f"{sound}{sound_uom or 'DBA'}".upper())
    invoice = " ".join(invoice_parts)
    row["INVOICE_DESC"] = invoice[:40]

    if "Whirlpool" in brand:
        mobile_lead = "Whirlpool"
    elif "FRIGIDAIRE" in brand.upper():
        mobile_lead = f"{manufacturer} FRIGIDAIRE"
    else:
        mobile_lead = brand.replace("®", "") or manufacturer
    mobile_parts = [f"{mobile_lead},", "Dishwasher,"]
    if series:
        mobile_parts.append(f"{series},")
    mobile_parts.append(mpn)
    if mounting:
        mobile_parts.append(f"{mounting} Mounting")
    row["MOBILE_DESC"] = " ".join(mobile_parts)[:80]

    short_parts = [brand, series, mpn, "Dishwasher"]
    if with_text:
        short_parts.insert(3, with_text.replace("With ", "With "))
    if mounting:
        short_parts.append(f"{mounting} Mounting")
    if cycles:
        short_parts.append(f"{cycles}-Wash Cycle")
    if material:
        short_parts.append(material)
    row["SHORT_DESC"] = ", ".join(part for part in short_parts if part)

    long_parts = [brand, "Dishwasher"]
    if with_text:
        long_parts.append(with_text)
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
    if material:
        long_parts.append(material)
    if color:
        long_parts.append(color)
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
        row["With"] = with_text
