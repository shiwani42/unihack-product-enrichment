from extract.evidence import Evidence, EvidenceBundle


def merge_bundles(*bundles: EvidenceBundle) -> EvidenceBundle:
    merged = EvidenceBundle()
    for bundle in bundles:
        if bundle.mfr_url and not merged.mfr_url:
            merged.mfr_url = bundle.mfr_url
        for ref in bundle.ref_urls:
            if ref not in merged.ref_urls:
                merged.ref_urls.append(ref)
        for item in bundle.items:
            merged.set(item)
    return merged
