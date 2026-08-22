"""Marketing and feature fields from manufacturer evidence for all categories."""

from extract.evidence import EvidenceBundle


def apply_marketing_fields(row: dict[str, str], bundle: EvidenceBundle) -> None:
    if bundle.marketing:
        row["MARKETING_DESCRIPTION"] = bundle.marketing[:2000]

    for index, feature in enumerate(bundle.features[:20], start=1):
        row[f"ITEM_FEATURES_{index}"] = feature[:240]

    if bundle.approvals and not row.get("Standard/Approvals"):
        row["Standard/Approvals"] = bundle.approvals
    if bundle.warranty and not row.get("Warranty"):
        row["Warranty"] = bundle.warranty
