from extract.evidence import EvidenceBundle
from ingest.csv_io import sanitize_cell
from ingest.csv_io import is_readable_text, sanitize_cell


def merge_bundles(*bundles: EvidenceBundle) -> EvidenceBundle:
    merged = EvidenceBundle()
    for bundle in bundles:
        if bundle.mfr_url and not merged.mfr_url:
            merged.mfr_url = bundle.mfr_url
        for ref in bundle.ref_urls:
            if ref not in merged.ref_urls:
                merged.ref_urls.append(ref)
        for image in getattr(bundle, "image_urls", []):
            if image not in merged.image_urls:
                merged.image_urls.append(image)
        marketing = sanitize_cell(bundle.marketing or "")
        if marketing and not merged.marketing:
            merged.marketing = marketing
        for feature in getattr(bundle, "features", []) or []:
            cleaned = sanitize_cell(feature)
            if cleaned and cleaned not in merged.features:
                merged.features.append(cleaned)
        if bundle.approvals and not merged.approvals:
            merged.approvals = bundle.approvals
        if bundle.warranty and not merged.warranty:
            merged.warranty = bundle.warranty
        for key, value in getattr(bundle, "product_ids", {}).items():
            merged.product_ids.setdefault(key, value)
        for item in bundle.items:
            merged.set(item)
    return merged
