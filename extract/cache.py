import json
from pathlib import Path

from extract.evidence import Evidence, EvidenceBundle
from io_utils import atomic_write_text, safe_filename

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "evidence_cache"


def cache_path(mpn: str) -> Path:
    return CACHE_DIR / f"{safe_filename(mpn)}.json"


def load_cached_bundle(mpn: str) -> EvidenceBundle | None:
    path = cache_path(mpn)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    bundle = EvidenceBundle(
        mfr_url=payload.get("mfr_url", ""),
        ref_urls=payload.get("ref_urls", []),
    )
    for item in payload.get("evidence", []):
        try:
            bundle.set(Evidence(**item))
        except TypeError:
            continue
    bundle.marketing = payload.get("marketing", "")
    bundle.features = payload.get("features", [])
    bundle.approvals = payload.get("approvals", "")
    bundle.warranty = payload.get("warranty", "")
    bundle.product_ids = payload.get("product_ids", {})
    bundle.image_urls = payload.get("image_urls", [])
    return bundle


def save_cached_bundle(mpn: str, bundle: EvidenceBundle) -> None:
    payload = {
        "mpn": safe_filename(mpn),
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
        "product_ids": getattr(bundle, "product_ids", {}),
        "image_urls": getattr(bundle, "image_urls", []),
    }
    atomic_write_text(cache_path(mpn), json.dumps(payload, indent=2))
