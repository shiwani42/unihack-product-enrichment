import re

from classify.category_router import CategoryTemplate
from extract.evidence import Evidence, EvidenceBundle
from normalize.units import normalize_dimension_list, split_value_uom


def _set(bundle: EvidenceBundle, field: str, value: str, uom: str, quote: str, confidence: float = 0.65) -> None:
    if not value:
        return
    bundle.set(
        Evidence(
            field=field,
            value=value,
            uom=uom,
            source_url="input:Part_Desc",
            quote=quote[:120],
            extractor="generic_desc_parser",
            confidence=confidence,
        )
    )


def extract_generic_from_desc(part_desc: str, mpn: str, template: CategoryTemplate) -> EvidenceBundle:
    bundle = EvidenceBundle()
    text = part_desc
    lower = text.lower()

    product_type = template.product_name
    if template.category_id == "led_lighting":
        if re.search(r"strip", lower):
            product_type = "LED Strip Light"
        elif re.search(r"ceiling", lower):
            product_type = "LED Ceiling Light"
        elif re.search(r"wall", lower):
            product_type = "Wall Light"
        elif re.search(r"bath", lower):
            product_type = "Bath Light"
    elif template.category_id == "deck_composite":
        product_type = "Composite Decking Board"
        if re.search(r"fascia", lower):
            product_type = "Composite Fascia Board"
        elif re.search(r"rail", lower):
            product_type = "Composite Railing"
    elif template.category_id == "pipe_fitting":
        product_type = "Pipe Coupling"
    elif template.category_id == "electrical_box":
        product_type = "Electrical Box Cover"
    elif template.category_id == "ceiling_fan":
        product_type = "Ceiling Fan"
    elif template.category_id == "cooking_range":
        if "electric" in lower:
            product_type = "Electric Range"
        elif "gas" in lower:
            product_type = "Gas Range"
        else:
            product_type = "Range"
    elif template.category_id == "power_tool_accessory":
        if "countersink" in lower or "drill" in lower:
            product_type = "Drill Bit"
        elif "blade" in lower:
            product_type = "Saw Blade"
        else:
            product_type = "Power Tool Accessory"
    elif template.category_id == "generic_industrial":
        if re.search(r"cplg|coupling", lower):
            product_type = "Coupling"
        elif re.search(r"elbow|tee|adapter|adpt", lower):
            product_type = "Pipe Fitting"
        elif re.search(r"mortar|grout", lower):
            product_type = "Mortar Mix"

    _set(bundle, "Product Type", product_type, "", text, 0.7 if template.category_id != "generic_industrial" else 0.55)

    dim_match = re.search(r"(\d+(?:-\d+/\d+)?(?:\.\d+)?(?:\"|in)?\s*[xX×]\s*\d+(?:-\d+/\d+)?(?:\.\d+)?(?:\"|in)?(?:\s*[xX×]\s*\d+(?:-\d+/\d+)?(?:\.\d+)?(?:\"|in)?)?)", text)
    if dim_match:
        size = normalize_dimension_list(dim_match.group(1))
        _set(bundle, "Size", size, "in", text)
        _set(bundle, "Length", size, "in", text)

    length = re.search(r"(\d+(?:'\d+)?|\d+(?:\.\d+)?)\s?(?:'|ft|foot|feet|\d+\s*in|\")", text, re.I)
    if length and not bundle.get("Length"):
        value, uom = split_value_uom(length.group(0).strip())
        _set(bundle, "Length", value, uom, text)
        _set(bundle, "Size", value, uom, text)

    width = re.search(r'(\d+(?:\.\d+)?)\s?(?:"|in)\s*(?:range|wide|w\b)', text, re.I)
    if width:
        _set(bundle, "Width", width.group(1), "in", text)

    blade_span = re.search(r'(\d+(?:\.\d+)?)\s?(?:"|in)\s*(?:wh|mb|bz)?\s*(?:gilmour|hunter|fan)', text, re.I)
    if blade_span:
        _set(bundle, "Blade Span", blade_span.group(1), "in", text)
    elif re.search(r"fan", lower):
        span = re.search(r'(\d+(?:\.\d+)?)\s?(?:"|in)', text)
        if span:
            _set(bundle, "Blade Span", span.group(1), "in", text)

    gang = re.search(r"(\d)\s?[gG]", text)
    if gang:
        _set(bundle, "Gang Count", gang.group(1), "", text)

    watt = re.search(r"(\d+(?:\.\d+)?)\s?[wW](?:att)?\b", text)
    if watt:
        _set(bundle, "Wattage", watt.group(1), "W", text)

    volt = re.search(r"(\d{2,3})\s?[vV]\b", text)
    if volt:
        _set(bundle, "Voltage Rating", volt.group(1), "V", text, 0.7)

    pressure = re.search(r"(\d+)\s?#", text)
    if pressure:
        _set(bundle, "Pressure Rating", pressure.group(1), "PSI", text)

    cct = re.search(r"(multi cct|\d{4}k)", text, re.I)
    if cct:
        _set(bundle, "Color Temperature", cct.group(1).title().replace("Cct", "CCT"), "", text)

    finish = re.search(r"\b(BK|Black|White|SS|Stainless|Bronze|Mocha|Chrome|Brass|BZ|BRS)\b", text, re.I)
    if finish:
        finish_map = {
            "bk": "Black",
            "ss": "Stainless Steel",
            "bz": "Bronze",
            "brs": "Brass",
        }
        value = finish_map.get(finish.group(1).lower(), finish.group(1).title())
        _set(bundle, "Finish", value, "", text)
        _set(bundle, "Color", value, "", text)

    material = re.search(r"\b(PVC|Aluminum|Steel|Stainless Steel|Plastic|Brass|Bronze|Galvanized)\b", text, re.I)
    if material:
        _set(bundle, "Material", material.group(1).title(), "", text)

    grit = re.search(r"\bP(\d{2,3})\b", text, re.I)
    if grit:
        _set(bundle, "Grit", f"P{grit.group(1)}", "", text)

    pack = re.search(r"(\d+)\s?(?:pc|pk|pack|box|disc)\b", text, re.I)
    if pack:
        _set(bundle, "Pack Quantity", pack.group(1), "", text)

    diameter = re.search(r'(\d+(?:-\d+/\d+)?|\d+(?:\.\d+)?)\s?(?:"|in\b)', text, re.I)
    if diameter and template.category_id in {"power_tool_accessory", "metal_cutoff_disc"}:
        _set(bundle, "Diameter", diameter.group(1), "in", text)

    fuel = re.search(r"\b(Electric|Gas|Dual Fuel)\b", text, re.I)
    if fuel:
        _set(bundle, "Fuel Type", fuel.group(1).title(), "", text)

    application = re.search(
        r"(Metal Cut Off Disc|Box Cover|Range|Fan|LED|Drill|Mortar|Coupling|Pipe Fitting|Electrical Box|Abrasive)",
        text,
        re.I,
    )
    if application:
        _set(bundle, "Application", application.group(1).title(), "", text)

    if not bundle.items:
        _set(bundle, "Product Type", product_type or "Industrial Product", "", text, 0.5)

    return bundle
