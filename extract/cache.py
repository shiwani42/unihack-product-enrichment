import json
from pathlib import Path

from extract.evidence import Evidence, EvidenceBundle

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "evidence_cache"


def cache_path(mpn: str) -> Path:
    return CACHE_DIR / f"{mpn.upper()}.json"


def load_cached_bundle(mpn: str) -> EvidenceBundle | None:
    path = cache_path(mpn)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    bundle = EvidenceBundle(
        mfr_url=payload.get("mfr_url", ""),
        ref_urls=payload.get("ref_urls", []),
    )
    for item in payload.get("evidence", []):
        bundle.set(Evidence(**item))
    bundle.marketing = payload.get("marketing", "")
    bundle.features = payload.get("features", [])
    bundle.approvals = payload.get("approvals", "")
    bundle.warranty = payload.get("warranty", "")
    return bundle


def save_cached_bundle(mpn: str, bundle: EvidenceBundle) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "mpn": mpn.upper(),
        "mfr_url": bundle.mfr_url,
        "ref_urls": bundle.ref_urls,
        "evidence": [
            {
                "field": item.field,
                "value": item.value,
                "uom": item.uom,
                "source_url": item.source_url,
                "quote": item.quote,
                "extractor": item.extractor,
                "confidence": item.confidence,
            }
            for item in bundle.items
        ],
        "marketing": getattr(bundle, "marketing", ""),
        "features": getattr(bundle, "features", []),
        "approvals": getattr(bundle, "approvals", ""),
        "warranty": getattr(bundle, "warranty", ""),
    }
    cache_path(mpn).write_text(json.dumps(payload, indent=2), encoding="utf-8")
