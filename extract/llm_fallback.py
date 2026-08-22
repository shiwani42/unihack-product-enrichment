"""Optional LLM structured extraction — fallback only, minimal tokens."""

import hashlib
import json
import os
import re
from pathlib import Path

import httpx

from app.config import (
    LLM_CACHE_DIR,
    LLM_MAX_CALLS_PER_RUN,
    LLM_MAX_DESC_CHARS,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_MODEL,
    is_llm_enabled,
)
from extract.evidence import Evidence, EvidenceBundle

# ~35 tokens — keep tiny; model returns compact JSON only
SYSTEM_PROMPT = (
    "Extract product attrs from distributor text. JSON only, empty string if unknown: "
    '{"product_type":"","size":"","material":"","finish":"","color":"","application":"","brand_guess":""}'
)

_FIELD_MAP = {
    "product_type": "Product Type",
    "size": "Size",
    "material": "Material",
    "finish": "Finish",
    "color": "Color",
    "application": "Application",
}

_call_count = 0


def reset_llm_call_budget() -> None:
    global _call_count
    _call_count = 0


def should_use_llm(
    *,
    identity_method: str,
    evidence_count: int,
    category_id: str,
    part_desc: str,
) -> bool:
    """Strict gates: only unknown identity, thin evidence, non-appliance generic rows."""
    if not is_llm_enabled():
        return False
    if _call_count >= LLM_MAX_CALLS_PER_RUN:
        return False
    if identity_method != "unknown":
        return False
    if evidence_count > 2:
        return False
    if category_id in {"built_in_dishwasher", "cooking_range"}:
        return False
    if len(part_desc.strip()) < 8:
        return False
    return True


def _cache_key(mpn: str, part_desc: str) -> str:
    payload = f"{mpn.upper()}|{part_desc.strip().lower()}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _load_cache(key: str) -> dict | None:
    path = LLM_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_cache(key: str, data: dict) -> None:
    LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (LLM_CACHE_DIR / f"{key}.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def _parse_llm_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def _bundle_from_data(data: dict, part_desc: str) -> EvidenceBundle | None:
    bundle = EvidenceBundle()
    for src, field in _FIELD_MAP.items():
        value = str(data.get(src, "")).strip()
        if value:
            bundle.set(
                Evidence(
                    field=field,
                    value=value,
                    source_url="llm:inference",
                    quote=part_desc[:120],
                    extractor="llm_fallback",
                    confidence=0.58,
                )
            )
    brand_guess = str(data.get("brand_guess", "")).strip()
    if brand_guess:
        bundle.product_ids["brand_guess"] = brand_guess
    return bundle if bundle.items else None


def infer_with_llm(part_desc: str, mpn: str) -> EvidenceBundle | None:
    global _call_count

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None

    short_desc = part_desc.strip()[:LLM_MAX_DESC_CHARS]
    cache_key = _cache_key(mpn, short_desc)
    cached = _load_cache(cache_key)
    if cached is not None:
        return _bundle_from_data(cached, short_desc)

    if _call_count >= LLM_MAX_CALLS_PER_RUN:
        return None

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{mpn}|{short_desc}"},
        ],
        "temperature": 0,
        "max_tokens": LLM_MAX_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
    }
    try:
        _call_count += 1
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = _parse_llm_json(content)
    except (httpx.HTTPError, KeyError, json.JSONDecodeError, IndexError):
        return None

    _save_cache(cache_key, data)
    return _bundle_from_data(data, short_desc)
