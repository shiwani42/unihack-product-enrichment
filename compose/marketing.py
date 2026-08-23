"""Marketing and feature fields from manufacturer evidence for all categories."""

from extract.evidence import EvidenceBundle
from ingest.csv_io import sanitize_cell


def apply_marketing_fields(row: dict[str, str], bundle: EvidenceBundle) -> None:
    marketing = sanitize_cell(bundle.marketing or "")
    if marketing:
        row["MARKETING_DESCRIPTION"] = marketing[:2000]

    slot = 1
    for feature in bundle.features:
        if slot > 20:
            break
        cleaned = sanitize_cell(feature)
        if cleaned:
            row[f"ITEM_FEATURES_{slot}"] = cleaned[:240]
            slot += 1

    if bundle.approvals and not row.get("Standard/Approvals"):
        row["Standard/Approvals"] = bundle.approvals
    if bundle.warranty and not row.get("Warranty"):
        row["Warranty"] = bundle.warranty
