"""Regression tests: uniform live-fetch opportunity + validation honesty."""

import pytest

import pipeline as pipeline_module
from extract.evidence import Evidence, EvidenceBundle
from ingest.csv_io import load_output_headers, read_input_rows
from app.config import DEFAULT_INPUT
from pipeline import _fetch_evidence, count_verified_items, enrich_input_row
from validate.rules import overall_confidence, validate_row


def _identity(domains: list[str]):
    from identity.brand_resolver import Identity

    return Identity(
        brand_key="Acme",
        brand_name="ACME",
        manufacturer_name="Acme Corp",
        method="test",
        confidence=0.8,
        domains=domains,
    )


def _row_by_mpn(mpn: str):
    return next(r for r in read_input_rows(DEFAULT_INPUT) if r["Mfg_Part_Num"] == mpn)


def test_generic_category_gets_same_fetch_opportunity(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(mpn, domains, max_urls=None, fetch_pdfs=True):
        calls["n"] += 1
        bundle = EvidenceBundle()
        bundle.set(
            Evidence(field="Material", value="Brass", source_url=f"https://acme.com/{mpn}", extractor="html", confidence=0.8)
        )
        return bundle

    monkeypatch.setattr(pipeline_module, "fetch_manufacturer_evidence", fake_fetch)
    monkeypatch.setenv("UNILOG_LIVE_FETCH", "1")
    bundle = _fetch_evidence("X1", "X1", _identity(["acme.com"]), EvidenceBundle(), "generic_industrial")
    assert calls["n"] == 1
    assert len(bundle.items) == 1


def test_rich_cached_bundle_skips_network_entirely(monkeypatch):
    from pathlib import Path

    from extract.evidence import Evidence

    cache_dir = Path(__file__).resolve().parents[1] / "data" / "evidence_cache"
    monkeypatch.setattr("extract.cache.CACHE_DIR", cache_dir)
    calls = {"n": 0}

    def fail_fetch(*args, **kwargs):
        calls["n"] += 1
        raise AssertionError("network must not be touched for cached SKUs")

    monkeypatch.setattr(pipeline_module, "fetch_manufacturer_evidence", fail_fetch)
    bundle = _fetch_evidence("PDSH4816AF", "PDSH4816AF", _identity(["frigidaire.com"]), EvidenceBundle(), "built_in_dishwasher")
    assert calls["n"] == 0
    assert len(bundle.items) >= 5


def test_live_fetch_env_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.delenv("UNILOG_LIVE_FETCH", raising=False)
    monkeypatch.setenv("UNILOG_LIVE_FETCH", "0")

    def fail_fetch(*args, **kwargs):
        raise AssertionError("kill switch must prevent network")

    monkeypatch.setattr(pipeline_module, "fetch_manufacturer_evidence", fail_fetch)
    bundle = _fetch_evidence("NOCACHE1", "NOCACHE1", _identity(["acme.com"]), EvidenceBundle(), "generic_industrial")
    assert len(bundle.items) == 0


def test_count_verified_excludes_self_cited_and_inferred():
    bundle = EvidenceBundle()
    bundle.set(Evidence(field="A", value="1", source_url="input:Part_Desc", extractor="desc_regex", confidence=0.7))
    bundle.set(Evidence(field="B", value="2", source_url="https://mfr.com/p", extractor="html", confidence=0.8))
    bundle.set(Evidence(field="C", value="3", source_url="input:Part_Desc", extractor="smart_infer", confidence=0.45))
    assert count_verified_items(bundle) == 1


def test_self_cited_only_evidence_cannot_reach_high_band():
    row = {"Product Name": "Widget", "Classpath": "A>B>C"}
    assert overall_confidence(row, 0.9, 0) == "review"
    assert overall_confidence(row, 0.9, 2) == "medium"


def test_verified_evidence_reaches_high_band():
    row = {"Product Name": "Widget", "Classpath": "A>B>C"}
    assert overall_confidence(row, 0.9, 5) == "high"


def test_validate_flags_empty_descriptions():
    row = {"Product Name": "Widget", "Classpath": "A>B>C"}
    issues = validate_row(row, category_id="generic_industrial")
    empty = {issue.field for issue in issues if "empty" in issue.message}
    assert {"MOBILE_DESC", "SHORT_DESC", "LONG_DESC1"} <= empty


def test_generic_row_enriches_end_to_end_offline():
    headers = load_output_headers()
    result = enrich_input_row(_row_by_mpn("3MABR-7100075678"), headers)
    assert result.row.get("BRAND_NAME")
    # Desc-only evidence is self-cited: honest band must never claim high.
    assert result.verified_evidence_count == 0
    assert result.confidence_band in {"review", "low", "medium"}
    assert result.confidence_band != "high"
