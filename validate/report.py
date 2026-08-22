from dataclasses import dataclass, asdict


@dataclass
class RowReport:
    mpn: str
    confidence_band: str
    evidence_count: int
    filled_fields: int
    issue_count: int
    issues: list[str]
    field_sources: dict[str, str]
    category_id: str = ""


def build_row_report(
    mpn: str,
    row: dict[str, str],
    confidence_band: str,
    evidence_count: int,
    issues,
    field_sources: dict[str, str] | None = None,
    category_id: str = "",
) -> RowReport:
    filled_fields = sum(1 for value in row.values() if (value or "").strip())
    issue_messages = [f"{issue.field}: {issue.message}" for issue in issues]
    return RowReport(
        mpn=mpn,
        confidence_band=confidence_band,
        evidence_count=evidence_count,
        filled_fields=filled_fields,
        issue_count=len(issues),
        issues=issue_messages,
        field_sources=field_sources or {},
        category_id=category_id,
    )


def summarize_reports(reports: list[RowReport]) -> dict:
    if not reports:
        return {"rows": 0}
    return {
        "rows": len(reports),
        "avg_filled_fields": round(sum(item.filled_fields for item in reports) / len(reports), 2),
        "avg_evidence_count": round(sum(item.evidence_count for item in reports) / len(reports), 2),
        "confidence_breakdown": {
            band: sum(1 for item in reports if item.confidence_band == band)
            for band in sorted(set(item.confidence_band for item in reports))
        },
        "rows_with_issues": sum(1 for item in reports if item.issue_count > 0),
    }


def reports_to_dicts(reports: list[RowReport]) -> list[dict]:
    return [asdict(item) for item in reports]
