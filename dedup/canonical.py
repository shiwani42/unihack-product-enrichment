"""Stage 2: De-duplication — canonical keys for same product across distributor spellings."""

from dataclasses import dataclass

from identity.brand_resolver import Identity
from ingest.input_analyzer import AnalyzedInput, normalize_mpn, strip_vendor_prefix


@dataclass(frozen=True)
class CanonicalProduct:
    brand_key: str
    normalized_mpn: str
    vendor_stripped_mpn: str

    @property
    def key(self) -> str:
        brand = self.brand_key or "UNKNOWN"
        return f"{brand}|{self.normalized_mpn}"


def canonical_product(analyzed: AnalyzedInput, identity: Identity) -> CanonicalProduct:
    mpn = analyzed.normalized_mpn or normalize_mpn(analyzed.raw_mpn)
    return CanonicalProduct(
        brand_key=identity.brand_key,
        normalized_mpn=mpn,
        vendor_stripped_mpn=strip_vendor_prefix(mpn),
    )


def dedupe_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, list[str]]]:
    """Return unique rows by raw MPN and map duplicate MPNS to canonical key."""
    seen: dict[str, dict[str, str]] = {}
    clusters: dict[str, list[str]] = {}
    unique: list[dict[str, str]] = []

    for row in rows:
        mpn = normalize_mpn(row.get("Mfg_Part_Num", ""))
        if mpn not in seen:
            seen[mpn] = row
            unique.append(row)
            clusters[mpn] = [mpn]
        else:
            clusters.setdefault(mpn, []).append(mpn)

    return unique, clusters


def cluster_keys(rows: list[dict[str, str]]) -> dict[str, list[int]]:
    """Group input-row indices by normalized MPN preserving first-seen order."""
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        key = normalize_mpn(row.get("Mfg_Part_Num", "")) or row.get("Mfg_Part_Num", "")
        groups.setdefault(key, []).append(index)
    return groups


def collapse_duplicates(rows: list, results: list) -> tuple[list, list]:
    """Merge enrichment results of duplicate MPNs instead of dropping them.

    The most complete row (most filled fields) becomes the representative;
    empty fields are backfilled from its duplicates, so no sourced evidence
    is lost.
    """
    if len(rows) != len(results):
        raise ValueError("rows and results must be aligned")

    groups = cluster_keys(rows)
    kept: list[int] = []
    merged_count = 0
    for indices in groups.values():
        if len(indices) == 1:
            kept.append(indices[0])
            continue

        def filled_count(index: int) -> int:
            return sum(1 for value in results[index].row.values() if value)

        base = max(indices, key=filled_count)
        for index in indices:
            if index == base:
                continue
            merged_count += 1
            for field, value in results[index].row.items():
                if value and not results[base].row.get(field):
                    results[base].row[field] = value
                    source = results[index].field_sources.get(field)
                    if source and field not in results[base].field_sources:
                        results[base].field_sources[field] = source
        kept.append(base)

    merged_rows = [rows[i] for i in kept]
    merged_results = [results[i] for i in kept]
    return merged_rows, merged_results
