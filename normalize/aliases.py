import json
from pathlib import Path

from classify.category_router import CategoryTemplate
from extract.evidence import Evidence, EvidenceBundle, is_self_cited

ALIASES_PATH = Path(__file__).resolve().parent / "field_aliases.json"


def _load_aliases() -> dict[str, list[str]]:
    if not ALIASES_PATH.exists():
        return {}
    return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))


def _norm_label(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def field_matches_label(field: str, label: str) -> bool:
    """True when a page label is the template field or a more specific spelling of it."""
    field_l = _norm_label(field)
    label_l = _norm_label(label)
    if not field_l or not label_l:
        return False
    return field_l == label_l or field_l.endswith(f" {label_l}")


def candidates_for_label(bundle: EvidenceBundle, label: str, aliases: dict[str, list[str]] | None = None) -> list[Evidence]:
    aliases = aliases if aliases is not None else _load_aliases()
    found: list[Evidence] = []
    seen: set[int] = set()

    def add(evidence: Evidence | None) -> None:
        if evidence is None or not (evidence.value or "").strip():
            return
        marker = id(evidence)
        if marker in seen:
            return
        seen.add(marker)
        found.append(evidence)

    add(bundle.get(label))
    for alt in aliases.get(label, []):
        add(bundle.get(alt))
    for item in bundle.items:
        if field_matches_label(item.field, label):
            add(item)
        else:
            for alt in aliases.get(label, []):
                if field_matches_label(item.field, alt):
                    add(item)
                    break
    return found


def pick_evidence_for_label(bundle: EvidenceBundle, label: str, aliases: dict[str, list[str]] | None = None):
    """Prefer a live manufacturer spec over a Part_Desc parse of the same slot."""
    found = candidates_for_label(bundle, label, aliases)
    if not found:
        return None
    live = [item for item in found if not is_self_cited(item.source_url)]
    pool = live or found
    return max(pool, key=lambda item: (item.confidence, len(item.source_url or "")))


def _copy(evidence: Evidence, field: str, confidence: float) -> Evidence:
    return Evidence(
        field=field,
        value=evidence.value,
        uom=evidence.uom,
        source_url=evidence.source_url,
        quote=evidence.quote,
        extractor=evidence.extractor,
        confidence=confidence,
    )


def align_bundle_to_template(bundle: EvidenceBundle, template: CategoryTemplate) -> EvidenceBundle:
    """Copy evidence onto template label names when aliases or suffixes match.

    A live manufacturer spec under a different label (Wheel Diameter, Outside
    Diameter) must replace a Part_Desc parse of the template field (Diameter).
    """
    aliases = _load_aliases()
    for label in template.attribute_labels:
        chosen = pick_evidence_for_label(bundle, label, aliases)
        if chosen is None:
            continue
        current = bundle.get(label)
        if current is chosen:
            continue
        if current is not None and is_self_cited(chosen.source_url):
            continue
        bundle.set(_copy(chosen, label, chosen.confidence))
    return bundle
