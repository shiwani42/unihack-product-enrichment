"""Tests: imported reference data activates LOV/UOM/manufacturer lookups."""

import json

import pytest

openpyxl = pytest.importorskip("openpyxl")

from identity.brand_resolver import Identity, canonicalize_with_reference
from validate.rules import validate_row


def _identity(brand="acme", mfr="Acme Corp"):
    return Identity(
        brand_key=brand,
        brand_name=brand,
        manufacturer_name=mfr,
        domains=[],
        confidence=0.6,
        method="test",
    )


def test_canonicalize_no_reference_file_is_identity(tmp_path, monkeypatch):
    monkeypatch.setattr("identity.brand_resolver.REFERENCE_MANUFACTURERS_PATH", tmp_path / "missing.json")
    identity = _identity()
    assert canonicalize_with_reference(identity, "") is identity


def test_canonicalize_upgrades_to_legal_casing(tmp_path, monkeypatch):
    ref = {
        "entries": [
            {"manufacturer_name": "Whirlpool Corporation", "brand_name": "Whirlpool®"},
            {"manufacturer_name": "Frigidaire Company", "brand_name": "FRIGIDAIRE®"},
        ]
    }
    path = tmp_path / "manufacturers.json"
    path.write_text(json.dumps(ref))
    monkeypatch.setattr("identity.brand_resolver.REFERENCE_MANUFACTURERS_PATH", path)
    monkeypatch.setattr("identity.brand_resolver._reference_index_cache", None)

    upgraded = canonicalize_with_reference(_identity("whirlpool", "Whirlpool Corporation"), "")
    assert upgraded.brand_name == "Whirlpool®"
    assert upgraded.manufacturer_name == "Whirlpool Corporation"
    assert upgraded.method.endswith("+unicat")

    # Exact-match only: a near-miss name must pass through untouched.
    untouched = canonicalize_with_reference(_identity("whirlpool corp", ""), "")
    assert untouched.brand_name == "whirlpool corp"
    assert untouched.method == "test"

    via_part_manuf = canonicalize_with_reference(
        _identity("unknown", ""), "Frigidaire Company (1234)"
    )
    assert via_part_manuf.brand_name == "FRIGIDAIRE®"


def test_validate_mounting_uses_reference_lov(tmp_path, monkeypatch):
    ref = {"values_by_label": {"Mounting Type": ["Leg", "Built-in", "Suspended"]}}
    path = tmp_path / "lov_values.json"
    path.write_text(json.dumps(ref))
    monkeypatch.setattr("validate.rules.REFERENCE_LOV_PATH", path)
    monkeypatch.setattr("validate.rules._reference_values_cache", None)

    row = {
        "Product Name": "Fan",
        "Classpath": "A>B>C",
        "ATTRIBUTE_LABEL 1": "Mounting Type",
        "ATTRIBUTE_VALUE 1": "Ceiling Mount",
    }
    issues = validate_row(row, category_id="ceiling_fan")
    assert any("not in LOV" in i.message for i in issues)

    ok = dict(row)
    ok["ATTRIBUTE_VALUE 1"] = "Suspended"
    assert not any("not in LOV" in i.message for i in validate_row(ok, category_id="ceiling_fan"))
