from dataclasses import dataclass


@dataclass
class ValidationIssue:
    field: str
    message: str
    severity: str


def validate_row(row: dict[str, str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    invoice = row.get("INVOICE_DESC", "")
    if invoice and len(invoice) > 40:
        issues.append(ValidationIssue("INVOICE_DESC", "exceeds 40 characters", "error"))

    mobile = row.get("MOBILE_DESC", "")
    if mobile:
        if len(mobile) < 60:
            issues.append(ValidationIssue("MOBILE_DESC", "below 60 characters", "warning"))
        if len(mobile) > 80:
            issues.append(ValidationIssue("MOBILE_DESC", "exceeds 80 characters", "error"))

    for index in range(1, 51):
        label = row.get(f"ATTRIBUTE_LABEL {index}", "")
        value = row.get(f"ATTRIBUTE_VALUE {index}", "")
        if label == "Voltage Rating" and value and row.get("Amperage Rating", ""):
            pass
        if label == "Voltage Rating" and value and "A" in value and "V" not in value:
            issues.append(
                ValidationIssue(
                    f"ATTRIBUTE_VALUE {index}",
                    "voltage field looks like amperage",
                    "error",
                )
            )
    return issues


def overall_confidence(row: dict[str, str], identity_confidence: float, evidence_count: int) -> str:
    if identity_confidence < 0.5:
        return "review"
    if evidence_count >= 5 and identity_confidence >= 0.7:
        return "high"
    if evidence_count >= 2:
        return "medium"
    if evidence_count >= 1:
        return "low"
    return "review"
