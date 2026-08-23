"""Specs hidden in JS page state (Next.js, Nuxt, application/json scripts).

Kichler/LG/Mirka often ship an empty HTML shell with the product in
``__NEXT_DATA__``. Reading that JSON is cheaper than launching Chromium
and works on Vercel, where Playwright is not useful.
"""

from __future__ import annotations

import json
import re

from extract.evidence import EvidenceBundle
from extract.structured import _walk
from ingest.csv_io import is_readable_text
from sources.page_ok import looks_like_pdf

_NEXT_DATA = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_NUXT = re.compile(r"window\.__NUXT__\s*=\s*(\{.*?\});\s*</script>", re.I | re.S)
_JSON_SCRIPT = re.compile(
    r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_INITIAL_STATE = re.compile(
    r"window\.(?:__INITIAL_STATE__|__PRELOADED_STATE__)\s*=\s*(\{.*?\});\s*(?:window|</script>)",
    re.I | re.S,
)


def _loads(raw: str):
    text = (raw or "").strip()
    if not text or len(text) > 2_000_000:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def embedded_json_blobs(html: str) -> list:
    blobs: list = []
    for pattern in (_NEXT_DATA, _JSON_SCRIPT, _NUXT, _INITIAL_STATE):
        for match in pattern.findall(html or ""):
            payload = _loads(match)
            if payload is not None:
                blobs.append(payload)
            if len(blobs) >= 8:
                return blobs
    return blobs


def extract_page_state(html: str, url: str) -> EvidenceBundle:
    bundle = EvidenceBundle(mfr_url=url)
    if looks_like_pdf(html) or not is_readable_text((html or "")[:4000]):
        return bundle
    for payload in embedded_json_blobs(html):
        _walk(payload, url, bundle)
    return bundle
