"""Leaf-level taxonomy matching via keyword/pattern scoring."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import TAXONOMY_PATH

TOKEN_RE = re.compile(r"[a-z0-9]+")


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


def _load_leaves() -> list[dict]:
    if not TAXONOMY_PATH.exists():
        return []
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


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
        score = 0.0
        for keyword in leaf.get("keywords", []):
            kw = keyword.lower()
            if kw in text:
                score += 2.0 + len(kw) * 0.05
            elif kw in desc_tokens:
                score += 1.5

        for pattern in leaf.get("patterns", []):
            if re.search(pattern, part_desc, re.I):
                score += 3.0

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
