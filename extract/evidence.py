import re
from dataclasses import dataclass, field


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

    def get(self, field: str) -> Evidence | None:
        for item in self.items:
            if item.field == field:
                return item
        return None

    def set(self, evidence: Evidence) -> None:
        existing = self.get(evidence.field)
        if existing and existing.confidence >= evidence.confidence:
            return
        self.items = [item for item in self.items if item.field != evidence.field]
        self.items.append(evidence)
