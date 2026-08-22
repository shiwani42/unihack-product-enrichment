from dataclasses import dataclass


@dataclass
class ReferenceDiff:
    field: str
    expected: str
    actual: str


@dataclass
class ReferenceScore:
    mpn: str
    expected_filled: int
    matches: int
    mismatches: list[ReferenceDiff]
    missing: list[str]
    extra: list[str]

    @property
    def score(self) -> float:
        if self.expected_filled == 0:
            return 0.0
        return self.matches / self.expected_filled


def compare_rows(expected: dict[str, str], actual: dict[str, str], mpn: str) -> ReferenceScore:
    mismatches: list[ReferenceDiff] = []
    missing: list[str] = []
    extra: list[str] = []
    expected_filled = 0
    matches = 0

    for field, expected_value in expected.items():
        expected_value = (expected_value or "").strip()
        actual_value = (actual.get(field) or "").strip()
        if not expected_value:
            if actual_value:
                extra.append(field)
            continue
        expected_filled += 1
        if actual_value == expected_value:
            matches += 1
        elif not actual_value:
            missing.append(field)
        else:
            mismatches.append(ReferenceDiff(field=field, expected=expected_value, actual=actual_value))

    return ReferenceScore(
        mpn=mpn,
        expected_filled=expected_filled,
        matches=matches,
        mismatches=mismatches,
        missing=missing,
        extra=extra,
    )
