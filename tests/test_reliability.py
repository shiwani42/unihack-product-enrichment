"""Regression tests: reliability primitives (atomic IO, retry, eviction, loop safety)."""

import asyncio
import json

from extract.cache import load_cached_bundle, save_cached_bundle
from io_utils import atomic_write_text, safe_filename
from sources.raw_cache import load_raw_html, save_raw_html
from sources.retry import call_with_retry


def test_safe_filename_blocks_traversal():
    assert safe_filename("../../etc/passwd") == "______ETC_PASSWD"
    assert "/" not in safe_filename("A/B/C")


def test_atomic_write_roundtrip(tmp_path):
    target = tmp_path / "nested" / "file.json"
    atomic_write_text(target, '{"ok": true}')
    assert json.loads(target.read_text()) == {"ok": True}


def test_load_cached_bundle_tolerates_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    corrupt = tmp_path / "BROKEN.json"
    corrupt.write_text('{"mpn": "BROKEN", "evidence": [')  # torn write
    assert load_cached_bundle("BROKEN") is None


def test_save_and_load_roundtrip_with_image_urls(tmp_path, monkeypatch):
    from extract.evidence import Evidence, EvidenceBundle

    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    bundle = EvidenceBundle(mfr_url="https://acme.com/p/X1")
    bundle.image_urls = ["https://acme.com/x1.jpg"]
    bundle.set(Evidence(field="Color", value="Black", source_url="https://acme.com/p/X1", extractor="test", confidence=0.9))
    save_cached_bundle("X1", bundle)

    loaded = load_cached_bundle("X1")
    assert loaded is not None
    assert loaded.mfr_url.endswith("/X1")
    assert loaded.image_urls == ["https://acme.com/x1.jpg"]
    assert loaded.get("Color").value == "Black"
    assert loaded.fetched_at
    assert loaded.content_hash


def test_evidence_cache_rejects_tampered_hash(tmp_path, monkeypatch):
    from extract.evidence import Evidence, EvidenceBundle

    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    bundle = EvidenceBundle(mfr_url="https://acme.com/p/X1")
    bundle.set(Evidence(field="Color", value="Black", source_url="https://acme.com/p/X1", extractor="html", confidence=0.9))
    save_cached_bundle("X1", bundle)

    path = tmp_path / "X1.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["value"] = "Red"
    path.write_text(json.dumps(payload, indent=2))
    assert load_cached_bundle("X1") is None


def test_evidence_cache_ttl_expires_stale_entries(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from extract.evidence import Evidence, EvidenceBundle

    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setattr("extract.cache.EVIDENCE_CACHE_TTL_DAYS", 7)
    bundle = EvidenceBundle(mfr_url="https://acme.com/p/OLD")
    bundle.set(Evidence(field="Color", value="Black", source_url="https://acme.com/p/OLD", extractor="html", confidence=0.9))
    stale = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    save_cached_bundle("OLD1", bundle, fetched_at=stale)
    assert load_cached_bundle("OLD1") is None

    save_cached_bundle("NEW1", bundle)
    assert load_cached_bundle("NEW1") is not None


def test_evidence_cache_unstamped_never_loads(tmp_path, monkeypatch):
    import os

    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setattr("extract.cache.EVIDENCE_CACHE_TTL_DAYS", 7)
    path = tmp_path / "LEGACY.json"
    path.write_text(json.dumps({
        "mpn": "LEGACY",
        "mfr_url": "https://acme.com/p/LEGACY",
        "evidence": [{"field": "Color", "value": "Black", "uom": "", "source_url": "https://acme.com/p/LEGACY", "quote": "black finish", "extractor": "html", "confidence": 0.8}],
    }))
    os.utime(path, None)
    assert load_cached_bundle("LEGACY") is None


def test_call_with_retry_recovers_from_transient_failures(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = {"count": 0}

    def flaky() -> tuple[int, str, str]:
        calls["count"] += 1
        if calls["count"] < 3:
            return 503, "", "http://x"
        return 200, "<html>ok</html>", "http://x"

    status, html, _ = call_with_retry(flaky, attempts=4, base_delay=0.01)
    assert status == 200 and html


def test_call_with_retry_does_not_retry_client_errors(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = {"count": 0}

    def forbidden() -> tuple[int, str, str]:
        calls["count"] += 1
        return 403, "", "http://x"

    call_with_retry(forbidden, attempts=3, base_delay=0.01)
    assert calls["count"] < 3


def test_raw_cache_eviction_respects_cap(tmp_path, monkeypatch):
    import time as time_mod

    import sources.raw_cache as raw_cache

    monkeypatch.setattr(raw_cache, "RAW_CACHE_DIR", tmp_path)
    monkeypatch.setattr(raw_cache, "RAW_CACHE_MAX_FILES", 2)
    for mpn in ("AAA", "BBB", "CCC"):
        save_raw_html(mpn, f"<html>{mpn}</html>", f"https://{mpn}.com")
        time_mod.sleep(0.01)
    names = sorted(p.name for p in tmp_path.glob("*.html"))
    assert len(names) <= 2
    assert "AAA.html" not in names


def test_raw_cache_ttl_expires_stale_entries(tmp_path, monkeypatch):
    import os
    import time as time_mod

    import sources.raw_cache as raw_cache

    monkeypatch.setattr(raw_cache, "RAW_CACHE_DIR", tmp_path)
    monkeypatch.setattr(raw_cache, "RAW_CACHE_TTL_DAYS", 0)
    path = save_raw_html("OLD1", "<html></html>", "https://old1.com")
    os.utime(path, (time_mod.time() - 86400, time_mod.time() - 86400))
    assert load_raw_html("OLD1") is None


def test_run_coroutine_blocking_works_inside_running_loop():
    from sources.live_enrich import _run_coroutine_blocking

    async def value():
        await asyncio.sleep(0)
        return 42

    async def caller():
        # Simulates FastAPI async endpoint context: a loop is already running.
        return _run_coroutine_blocking(value())

    assert asyncio.run(caller()) == 42
