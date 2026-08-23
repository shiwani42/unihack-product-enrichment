"""When Part_Desc already filled a field, cite the manufacturer page if it repeats the value.

Blade span ``44`` from ``44" Wh Gilmour Fan`` stays honest as input:Part_Desc
until the manufacturer HTML actually contains that measurement. Then the
source becomes the manufacturer URL without inventing a new value.
"""

from __future__ import annotations

from extract.evidence import EvidenceBundle

_SELF = ("input:",)


def _page_confirms(value: str, field: str, uom: str, html: str) -> bool:
    text = html or ""
    needle = (value or "").strip()
    if len(needle) < 2:
        return False
    lowered = text.lower()
    field_l = (field or "").lower()
    uom_l = (uom or "").lower()
    compact = needle.lower()
    phrases = [compact]
    if uom_l:
        phrases.append(f"{compact} {uom_l}")
        if uom_l in {"in", "inch", "inches"}:
            phrases.append(f'{compact}"')
            phrases.append(f"{compact}-inch")
            phrases.append(f"{compact} inch")
    short_numeric = compact.replace(".", "").isdigit() and len(compact) <= 3
    for phrase in phrases:
        start = 0
        while True:
            idx = lowered.find(phrase, start)
            if idx < 0:
                break
            window = lowered[max(0, idx - 48) : idx + len(phrase) + 48]
            if field_l in {"finish", "color"}:
                if any(token in window for token in ("finish", "color", "colour")):
                    return True
            elif short_numeric:
                tokens = [token for token in field_l.split() if len(token) > 3]
                nearby = any(token in window for token in tokens) or any(
                    token in window for token in ("span", "blade", "watt", "volt", "amp")
                )
                unitish = '"' in window or "inch" in window
                if nearby or unitish:
                    return True
            else:
                return True
            start = idx + len(phrase)
    return False


def confirm_desc_evidence(bundle: EvidenceBundle, html: str, url: str, manufacturer_domains: list[str]) -> None:
    from sources.finder import is_search_url
    from sources.source_policy import is_primary_url

    if not html or not url or is_search_url(url):
        return
    if not is_primary_url(url, manufacturer_domains):
        return
    for item in bundle.items:
        source = (item.source_url or "").lower()
        if not source.startswith(_SELF):
            continue
        if _page_confirms(item.value, item.field, item.uom, html):
            item.source_url = url
            item.confidence = max(item.confidence, 0.7)
