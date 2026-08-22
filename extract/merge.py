from extract.evidence import EvidenceBundle


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
        if bundle.marketing and not merged.marketing:
            merged.marketing = bundle.marketing
        for feature in getattr(bundle, "features", []) or []:
            if feature not in merged.features:
                merged.features.append(feature)
        if bundle.approvals and not merged.approvals:
            merged.approvals = bundle.approvals
        if bundle.warranty and not merged.warranty:
            merged.warranty = bundle.warranty
        for key, value in getattr(bundle, "product_ids", {}).items():
            merged.product_ids.setdefault(key, value)
        for item in bundle.items:
            merged.set(item)
    return merged
