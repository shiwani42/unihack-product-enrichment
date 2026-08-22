"""Regression tests: dedup merges duplicate rows instead of dropping them."""

from dedup.canonical import collapse_duplicates, cluster_keys


class _Result:
    def __init__(self, row: dict, sources: dict | None = None):
        self.row = row
        self.field_sources = sources or {}


def test_cluster_keys_groups_normalized_mpns():
    rows = [
        {"Mfg_Part_Num": "ABC-123"},
        {"Mfg_Part_Num": "abc-123"},
        {"Mfg_Part_Num": "XYZ-9"},
    ]
    groups = cluster_keys(rows)
    assert len(groups) == 2


def test_collapse_duplicates_merges_fields():
    rows = [{"Mfg_Part_Num": "A1"}, {"Mfg_Part_Num": "a1"}]
    results = [
        _Result({"F1": "", "F2": "from-first"}, {"F2": "src1"}),
        _Result({"F1": "from-second", "F2": ""}, {"F1": "src2"}),
    ]
    merged_rows, merged_results = collapse_duplicates(rows, results)
    assert len(merged_rows) == 1
    merged = merged_results[0].row
    assert merged["F1"] == "from-second"
    assert merged["F2"] == "from-first"
    assert merged_results[0].field_sources["F1"] == "src2"


def test_collapse_prefers_most_complete_row_as_base():
    rows = [{"Mfg_Part_Num": "B2"}, {"Mfg_Part_Num": "b2"}]
    thin = _Result({"Only": "thin"})
    rich = _Result({f"F{i}": f"v{i}" for i in range(5)})
    _, merged_results = collapse_duplicates(rows, [thin, rich])
    assert merged_results[0].row.get("F4") == "v4"


def test_unique_rows_pass_through():
    rows = [{"Mfg_Part_Num": "C1"}, {"Mfg_Part_Num": "D2"}]
    results = [_Result({"A": "1"}), _Result({"B": "2"})]
    merged_rows, merged_results = collapse_duplicates(rows, results)
    assert len(merged_rows) == 2
    assert merged_rows == rows
