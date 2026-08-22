"""Manufacturer evidence cache.

TTL matches the raw HTML cache so a revised spec sheet cannot outlive the
page it was mined from. Every write stamps ``fetched_at`` (UTC) and a
content hash; loads with a mismatched hash or expired age are ignored.
Unstamped files are treated as precooked seeds and never loaded.
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import EVIDENCE_CACHE_DIR, EVIDENCE_CACHE_TTL_DAYS
from extract.evidence import Evidence, EvidenceBundle
from io_utils import atomic_write_text, safe_filename

CACHE_DIR = EVIDENCE_CACHE_DIR

_HASH_KEYS = (
    "mfr_url",
    "ref_urls",
    "evidence",
    "marketing",
    "features",
    "approvals",
    "warranty",
    "product_ids",
    "image_urls",
)


def cache_path(mpn: str) -> Path:
    return CACHE_DIR / f"{safe_filename(mpn)}.json"


def _hashable(payload: dict) -> dict:
    return {key: payload.get(key) for key in _HASH_KEYS}


def content_hash(payload: dict) -> str:
    blob = json.dumps(_hashable(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _age_days(payload: dict, path: Path) -> float:
    fetched = (payload.get("fetched_at") or "").strip()
    if fetched:
        try:
            stamp = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds() / 86400
        except ValueError:
            pass
    try:
        return (time.time() - path.stat().st_mtime) / 86400
    except OSError:
        return float("inf")


def _bundle_from_payload(payload: dict) -> EvidenceBundle:
    bundle = EvidenceBundle(
        mfr_url=payload.get("mfr_url", ""),
        ref_urls=payload.get("ref_urls", []),
        fetched_at=payload.get("fetched_at", ""),
        content_hash=payload.get("content_hash", ""),
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


def load_cached_bundle(mpn: str) -> EvidenceBundle | None:
    path = cache_path(mpn)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    stored_hash = (payload.get("content_hash") or "").strip()
    if stored_hash and stored_hash != content_hash(payload):
        return None
    # Unstamped files are seed/precooked lookups, not live fetches.
    if not (payload.get("fetched_at") or "").strip():
        return None
    if _age_days(payload, path) > EVIDENCE_CACHE_TTL_DAYS:
        return None
    return _bundle_from_payload(payload)


def save_cached_bundle(mpn: str, bundle: EvidenceBundle, fetched_at: str | None = None) -> None:
    stamp = fetched_at or datetime.now(timezone.utc).isoformat()
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
        "fetched_at": stamp,
    }
    payload["content_hash"] = content_hash(payload)
    try:
        atomic_write_text(cache_path(mpn), json.dumps(payload, indent=2))
    except OSError:
        return
