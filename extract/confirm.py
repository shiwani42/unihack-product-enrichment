"""When Part_Desc already filled a field, cite the manufacturer page if it repeats the value.

Blade span ``44`` from ``44" Wh Gilmour Fan`` stays honest as input:Part_Desc
until the manufacturer HTML actually contains that measurement. Then the
source becomes the manufacturer URL without inventing a new value.
"""

from __future__ import annotations

import html as html_lib
import re

from extract.evidence import EvidenceBundle, is_self_cited, normalize_evidence_value


def _needles(value: str, uom: str) -> list[str]:
    raw = html_lib.unescape(value or "").strip()
    if len(raw) < 2:
        return []
    compact = raw.lower()
    phrases = [compact]
    stripped = compact.strip(" \"'")
    if stripped not in phrases:
        phrases.append(stripped)
    if uom:
        uom_l = uom.lower()
        phrases.append(f"{stripped} {uom_l}")
        if uom_l in {"in", "inch", "inches"}:
            phrases.append(f'{stripped}"')
            phrases.append(f"{stripped}-inch")
            phrases.append(f"{stripped} inch")
            phrases.append(f"{stripped} in")
    numeric = normalize_evidence_value(raw, uom)
    if numeric and numeric not in phrases:
        phrases.append(numeric)
        if (uom or "").lower() in {"in", "inch", "inches"} or raw.endswith('"'):
            phrases.append(f'{numeric}"')
            phrases.append(f"{numeric} in")
            phrases.append(f"{numeric}-inch")
    seen: set[str] = set()
    ordered: list[str] = []
    for phrase in phrases:
        key = phrase.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(phrase)
    return ordered


def _page_confirms(value: str, field: str, uom: str, html: str) -> bool:
    text = html_lib.unescape(html or "")
    if not text:
        return False
    lowered = text.lower()
    field_l = (field or "").lower()
    phrases = _needles(value, uom)
    if not phrases:
        return False
    short_numeric = bool(re.fullmatch(r"[\d.]+", normalize_evidence_value(value, uom))) and len(
        normalize_evidence_value(value, uom)
    ) <= 3
    for phrase in phrases:
        start = 0
        needle = phrase.lower()
        while True:
            idx = lowered.find(needle, start)
            if idx < 0:
                break
            window = lowered[max(0, idx - 48) : idx + len(needle) + 48]
            if field_l in {"finish", "color"}:
                if any(token in window for token in ("finish", "color", "colour")):
                    return True
            elif short_numeric:
                tokens = [token for token in field_l.split() if len(token) > 3]
                nearby = any(token in window for token in tokens) or any(
                    token in window for token in ("span", "blade", "watt", "volt", "amp", "diameter", "arbor", "grit")
                )
                unitish = '"' in window or "inch" in window
                if nearby or unitish:
                    return True
            else:
                return True
            start = idx + len(needle)
    return False


def confirm_desc_evidence(bundle: EvidenceBundle, html: str, url: str, manufacturer_domains: list[str]) -> None:
    from sources.finder import is_blocked_url, is_search_url

    if not html or not url or is_search_url(url) or is_blocked_url(url):
        return
    _ = manufacturer_domains
    for item in bundle.items:
        source = item.source_url or ""
        if not is_self_cited(source):
            continue
        if _page_confirms(item.value, item.field, item.uom, html):
            item.source_url = url
            item.confidence = max(item.confidence, 0.7)
