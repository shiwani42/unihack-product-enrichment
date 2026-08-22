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
    "material": "Material",
    "depth": "Depth With Door Open",
    "height": "Size",
    "width": "Size",
    "weight": "Additional Information",
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
    "model": "model",
}


def _normalize_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _walk(obj, url: str, bundle: EvidenceBundle) -> None:
    if isinstance(obj, dict):
        obj_type = str(obj.get("@type", "")).lower()
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
        data = extruct.extract(html, base_url=base, syntaxes=["json-ld", "microdata", "opengraph"])
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
            for key in ("og:upc", "product:upc", "og:ean"):
                if first.get(key):
                    bundle.product_ids["upc"] = str(first[key]).strip()

    return bundle
