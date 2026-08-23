"""Leaf-level taxonomy matching via keyword/pattern scoring."""

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import TAXONOMY_PATH

TOKEN_RE = re.compile(r"[a-z0-9]+")
OFFICIAL_LEAVES_PATH = Path(__file__).resolve().parents[1] / "data" / "taxonomy" / "official_leaves.json"


@dataclass
class TaxonomyMatch:
    leaf_id: str
    classpath: str
    dept: str
    class_name: str
    fine: str
    product_name: str
    template_id: str
    score: float
    confidence: float


def reset_leaf_cache() -> None:
    _load_leaves.cache_clear()


def _official_leaves_path() -> Path:
    override = os.environ.get("UNILOG_OFFICIAL_LEAVES", "").strip()
    return Path(override) if override else OFFICIAL_LEAVES_PATH


@lru_cache(maxsize=1)
def _load_leaves() -> tuple:
    bundled: list[dict] = []
    if TAXONOMY_PATH.exists():
        try:
            bundled = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            bundled = []
        if not isinstance(bundled, list):
            bundled = []
    official: list[dict] = []
    official_path = _official_leaves_path()
    if official_path.exists():
        try:
            payload = json.loads(official_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        if isinstance(payload, list):
            official = payload
        elif isinstance(payload, dict):
            official = payload.get("leaves") or []
    by_cp: dict[str, dict] = {}
    for leaf in bundled:
        key = str(leaf.get("classpath") or leaf.get("leaf_id") or "")
        if key:
            by_cp[key] = leaf
    for leaf in official:
        key = str(leaf.get("classpath") or leaf.get("leaf_id") or "")
        if key:
            by_cp[key] = leaf
    return tuple(by_cp.values())


def _tokens(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def match_taxonomy(part_desc: str, brand_key: str = "") -> TaxonomyMatch | None:
    leaves = _load_leaves()
    if not leaves:
        return None

    text = part_desc.lower()
    desc_tokens = _tokens(part_desc)
    brand_tokens = _tokens(brand_key) if brand_key else set()
    best: TaxonomyMatch | None = None

    for leaf in leaves:
        product_hit = False
        score = 0.0
        for keyword in leaf.get("keywords", []):
            kw = keyword.lower()
            if kw in text:
                score += 2.0 + len(kw) * 0.05
                product_hit = True
            elif kw in desc_tokens:
                score += 1.5
                product_hit = True

        for pattern in leaf.get("patterns", []):
            if re.search(pattern, part_desc, re.I):
                score += 3.0
                product_hit = True

        if not product_hit:
            continue

        for brand in leaf.get("brands", []):
            if brand_key and brand.lower() == brand_key.lower():
                score += 2.5
            if brand.lower() in text:
                score += 1.0

        if brand_tokens & set(t.lower() for t in leaf.get("brands", [])):
            score += 1.5

        if score <= 0:
            continue

        confidence = min(0.95, 0.35 + score * 0.08)
        candidate = TaxonomyMatch(
            leaf_id=leaf["leaf_id"],
            classpath=leaf["classpath"],
            dept=leaf["dept"],
            class_name=leaf["class"],
            fine=leaf["fine"],
            product_name=leaf.get("product_name", leaf["fine"]),
            template_id=leaf["template_id"],
            score=score,
            confidence=confidence,
        )
        if not best or candidate.score > best.score:
            best = candidate

    if best and best.score >= 2.0:
        return best
    return None
