import re

import extruct
from w3lib.html import get_base_url

from extract.evidence import Evidence, EvidenceBundle

PROPERTY_MAP = {
    "voltage": "Voltage Rating",
    "inputvoltage": "Voltage Rating",
    "amperage": "Amperage Rating",
    "current": "Amperage Rating",
    "soundlevel": "Sound Level",
    "noiselevel": "Sound Level",
    "color": "Color",
    "colour": "Color",
    "finish": "Finish",
    "material": "Material",
    "depth": "Depth With Door Open",
    "height": "Size",
    "width": "Size",
    "bladesspan": "Blade Span",
    "bladespan": "Blade Span",
    "diameter": "Diameter",
    "wheeldiameter": "Diameter",
    "discdiameter": "Diameter",
    "wattage": "Wattage",
    "watts": "Wattage",
    "weight": "Weight",
    "arbor": "Arbor Size",
    "arborsize": "Arbor Size",
    "bore": "Arbor Size",
    "thickness": "Thickness",
    "grit": "Grit",
    "gritsize": "Grit",
    "maxrpm": "Maximum RPM",
    "maximumrpm": "Maximum RPM",
    "packquantity": "Pack Quantity",
    "packqty": "Pack Quantity",
    "packagequantity": "Pack Quantity",
    "sellingquantity": "Pack Quantity",
    "abrasivematerial": "Abrasive Material",
    "grain": "Abrasive Material",
    "application": "Application",
    "producttype": "Product Type",
    "includes": "Includes",
    "with": "With",
    "prop65": "Prop 65",
    "proposition65": "Prop 65",
    "warranty": "Warranty",
    "gtin": "GTIN",
    "upc": "UPC",
    "ean": "EAN",
    "unspsc": "UNSPSC",
    "countryoforigin": "Country Of Origin",
    "netweight": "Weight",
    "itemweight": "Weight",
    "productweight": "Weight",
    "overalllength": "Length",
    "itemlength": "Length",
}

_ID_EVIDENCE_FIELDS = {
    "gtin": "GTIN",
    "gtin13": "GTIN",
    "gtin12": "UPC",
    "gtin8": "EAN",
    "upc": "UPC",
    "ean": "EAN",
    "unspsc": "UNSPSC",
    "countryoforigin": "Country Of Origin",
    "country": "Country Of Origin",
}

ID_KEYS = {
    "sku": "sku",
    "productid": "productid",
    "mpn": "mpn",
    "gtin13": "gtin13",
    "gtin12": "gtin12",
    "gtin8": "gtin8",
    "upc": "upc",
    "ean": "ean",
    "unspsc": "unspsc",
    "gtin": "gtin",
    "countryoforigin": "countryoforigin",
    "country": "country",
    "model": "model",
}


_SKIP_SPEC_KEYS = frozenset(
    {
        "price",
        "availability",
        "url",
        "image",
        "description",
        "offers",
        "brand",
        "seller",
        "shipping",
        "position",
        "type",
        "id",
        "itemid",
        "item",
        "review",
        "rating",
        "aggregaterating",
        "ratingvalue",
        "pricecurrency",
        "itemcondition",
        "availabilitystarts",
        "charset",
        "viewport",
        "keywords",
        "canonical",
        "robots",
        "ogtitle",
        "ogurl",
        "ogtype",
    }
)


def _normalize_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _field_from_spec_name(label: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", (label or "").strip())
    if not cleaned:
        return None
    norm = _normalize_key(cleaned)
    if norm in PROPERTY_MAP:
        return PROPERTY_MAP[norm]
    if norm in _ID_EVIDENCE_FIELDS:
        return _ID_EVIDENCE_FIELDS[norm]
    if norm in ID_KEYS or norm in _SKIP_SPEC_KEYS:
        return None
    if len(cleaned) > 48 or len(cleaned.split()) > 8:
        return None
    if not re.search(r"[A-Za-z]", cleaned):
        return None
    return cleaned


def _set_spec(bundle: EvidenceBundle, field: str, text: str, url: str, quote: str, confidence: float) -> None:
    if not field or not text:
        return
    if text.lower() in {"true", "false", "null", "none"}:
        return
    if len(text) > 80:
        return
    bundle.set(
        Evidence(
            field=field,
            value=text,
            source_url=url,
            quote=quote[:180],
            extractor="extruct",
            confidence=confidence,
        )
    )


def _walk(obj, url: str, bundle: EvidenceBundle) -> None:
    if isinstance(obj, dict):
        obj_type = str(obj.get("@type", "")).lower()
        lowered = {str(key).lower(): key for key in obj}
        name_key = next((lowered[key] for key in ("name", "label", "specname", "attributename") if key in lowered), None)
        value_key = next((lowered[key] for key in ("value", "specvalue", "attributevalue") if key in lowered), None)
        if name_key and value_key:
            field = _field_from_spec_name(str(obj.get(name_key) or ""))
            raw_value = obj.get(value_key)
            name_norm = _normalize_key(str(obj.get(name_key) or ""))
            if name_norm in ID_KEYS and isinstance(raw_value, (str, int, float)):
                text = str(raw_value).strip()
                if text and name_norm not in bundle.product_ids:
                    bundle.product_ids[ID_KEYS[name_norm]] = text
            if field and isinstance(raw_value, (str, int, float)):
                text = str(raw_value).strip()
                mapped = name_norm in PROPERTY_MAP or name_norm in _ID_EVIDENCE_FIELDS
                _set_spec(
                    bundle,
                    field,
                    text,
                    url,
                    f"{obj.get(name_key)}={text}",
                    0.82 if mapped else 0.78,
                )
        for key, value in obj.items():
            norm = _normalize_key(str(key))
            if norm in ID_KEYS and isinstance(value, (str, int, float)):
                text = str(value).strip()
                if text and norm not in bundle.product_ids:
                    bundle.product_ids[ID_KEYS[norm]] = text
            if norm in PROPERTY_MAP and isinstance(value, (str, int, float)):
                field = PROPERTY_MAP[norm]
                text = str(value).strip()
                if not text:
                    continue
                bundle.set(
                    Evidence(
                        field=field,
                        value=text,
                        source_url=url,
                        quote=f"{key}={text}"[:180],
                        extractor="extruct",
                        confidence=0.82,
                    )
                )
            if norm == "name" and "product" in obj_type and isinstance(value, str):
                if not bundle.get("Product Type"):
                    bundle.set(
                        Evidence(
                            field="Product Type",
                            value=value.strip()[:120],
                            source_url=url,
                            quote=value[:120],
                            extractor="extruct",
                            confidence=0.75,
                        )
                    )
            if norm == "image" and isinstance(value, str) and value.startswith("http"):
                if value not in bundle.image_urls:
                    bundle.image_urls.append(value.strip())
            _walk(value, url, bundle)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, url, bundle)


def extract_structured_data(html: str, url: str) -> EvidenceBundle:
    bundle = EvidenceBundle(mfr_url=url)
    try:
        base = get_base_url(html, url)
        syntaxes = ["json-ld", "opengraph"]
        # Microdata walks the whole DOM. On 1MB+ Shopify pages json-ld already
        # has the product; the extra parse is seconds of CPU for nothing.
        if len(html or "") < 350_000:
            syntaxes.append("microdata")
        data = extruct.extract(html, base_url=base, syntaxes=syntaxes)
    except Exception:
        return bundle

    for _, items in data.items():
        if items:
            _walk(items, url, bundle)

    og_items = data.get("opengraph") or []
    if og_items and isinstance(og_items, list):
        first = og_items[0] if og_items else {}
        if isinstance(first, dict):
            desc = first.get("og:description") or first.get("description")
            if desc and len(desc) > 40:
                bundle.marketing = str(desc).strip()[:1200]
            image = first.get("og:image") or first.get("og:image:url") or first.get("og:image:secure_url")
            if image and str(image).startswith("http"):
                bundle.image_urls.append(str(image).strip())
            for key, dest in (
                ("og:upc", "upc"),
                ("product:upc", "upc"),
                ("og:ean", "ean"),
                ("product:ean", "ean"),
                ("og:gtin", "gtin"),
                ("product:gtin", "gtin"),
            ):
                if first.get(key):
                    bundle.product_ids.setdefault(dest, str(first[key]).strip())

    return bundle
