import html as html_lib
import re
from dataclasses import dataclass, field

_SELF_PREFIX = "input:"
_UNIT_SUFFIX = re.compile(
    r"""[\s\-]*(?:inches|inch|in|"|mm|cm|volts?|v|amps?|a|watts?|w|rpm)\s*$""",
    re.I,
)


def is_self_cited(source_url: str) -> bool:
    return (source_url or "").lower().startswith(_SELF_PREFIX)


def normalize_evidence_value(value: str, uom: str = "") -> str:
    """Collapse 5 / 5" / 5 in / 5-inch so manufacturer text can match Part_Desc."""
    text = html_lib.unescape(value or "").strip().lower()
    for src in ("″", "”", "“", "\u2033", "\u2032"):
        text = text.replace(src, '"')
    text = re.sub(r"\s+", " ", text).strip(" \t\"'")
    core = _UNIT_SUFFIX.sub("", text).strip()
    if uom:
        core = re.sub(rf"\s*{re.escape(uom.strip())}\s*$", "", core, flags=re.I).strip()
    candidate = core if re.fullmatch(r"[\d./]+", core.replace(" ", "")) else text
    candidate = candidate.replace(" ", "")
    if re.fullmatch(r"\d+\.0+", candidate):
        candidate = candidate.split(".", 1)[0]
    if re.fullmatch(r"\.\d+", candidate):
        candidate = "0" + candidate
    return candidate


def values_equivalent(left: str, right: str, uom: str = "") -> bool:
    a = normalize_evidence_value(left, uom)
    b = normalize_evidence_value(right, uom)
    return bool(a) and a == b


@dataclass
class Evidence:
    field: str
    value: str
    uom: str = ""
    source_url: str = ""
    quote: str = ""
    extractor: str = ""
    confidence: float = 0.0


@dataclass
class EvidenceBundle:
    mfr_url: str = ""
    ref_urls: list[str] = field(default_factory=list)
    items: list[Evidence] = field(default_factory=list)
    marketing: str = ""
    features: list[str] = field(default_factory=list)
    approvals: str = ""
    warranty: str = ""
    product_ids: dict[str, str] = field(default_factory=dict)
    image_urls: list[str] = field(default_factory=list)
    fetched_at: str = ""
    content_hash: str = ""

    def get(self, field: str) -> Evidence | None:
        want = (field or "").strip().lower()
        if not want:
            return None
        for item in self.items:
            if item.field.lower() == want:
                return item
        return None

    def set(self, evidence: Evidence) -> None:
        existing = self.get(evidence.field)
        if existing and not _should_replace(existing, evidence):
            if _should_rehome(existing, evidence):
                existing.source_url = evidence.source_url
                existing.confidence = max(existing.confidence, evidence.confidence)
                if evidence.uom and not existing.uom:
                    existing.uom = evidence.uom
                if evidence.quote:
                    existing.quote = evidence.quote
            return
        want = (evidence.field or "").strip().lower()
        self.items = [item for item in self.items if item.field.lower() != want]
        self.items.append(evidence)


def _should_rehome(existing: Evidence, new: Evidence) -> bool:
    """Same measurement from a manufacturer page: keep the Part_Desc wording, cite the page."""
    if not is_self_cited(existing.source_url) or is_self_cited(new.source_url):
        return False
    return values_equivalent(existing.value, new.value, existing.uom or new.uom)


def _should_replace(existing: Evidence, new: Evidence) -> bool:
    existing_self = is_self_cited(existing.source_url)
    new_self = is_self_cited(new.source_url)
    if existing_self and not new_self:
        if values_equivalent(existing.value, new.value, existing.uom or new.uom):
            return False
        return new.confidence >= existing.confidence
    return new.confidence > existing.confidence
