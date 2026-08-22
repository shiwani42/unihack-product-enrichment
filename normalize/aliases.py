import json
from pathlib import Path

from classify.category_router import CategoryTemplate
from extract.evidence import Evidence, EvidenceBundle

ALIASES_PATH = Path(__file__).resolve().parent / "field_aliases.json"


def _load_aliases() -> dict[str, list[str]]:
    if not ALIASES_PATH.exists():
        return {}
    return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))


def align_bundle_to_template(bundle: EvidenceBundle, template: CategoryTemplate) -> EvidenceBundle:
    """Copy evidence items onto template label names when aliases match."""
    aliases = _load_aliases()
    for label in template.attribute_labels:
        if bundle.get(label):
            continue
        for alt in aliases.get(label, []):
            evidence = bundle.get(alt)
            if evidence:
                bundle.set(
                    Evidence(
                        field=label,
                        value=evidence.value,
                        uom=evidence.uom,
                        source_url=evidence.source_url,
                        quote=evidence.quote,
                        extractor=evidence.extractor,
                        confidence=evidence.confidence * 0.95,
                    )
                )
                break
        if not bundle.get(label):
            for item in bundle.items:
                if item.field.lower() == label.lower():
                    bundle.set(
                        Evidence(
                            field=label,
                            value=item.value,
                            uom=item.uom,
                            source_url=item.source_url,
                            quote=item.quote,
                            extractor=item.extractor,
                            confidence=item.confidence,
                        )
                    )
                    break
    return bundle
