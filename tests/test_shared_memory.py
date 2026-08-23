"""Shared URL memory is optional and fail-open without store credentials."""

from sources.shared_memory import configured, load_shared, merge_memory, save_shared
from sources.url_store import persist_shared


def test_merge_memory_unions_hosts_and_templates():
    base = {
        "known_urls": {"A": ["https://a.com/A"]},
        "search_paths": {"a.com": ["https://a.com/p/{mpn}"]},
        "dead_paths": {"a.com": {}},
        "search_engine": "bing",
    }
    overlay = {
        "known_urls": {"A": ["https://a.com/A"], "B": ["https://b.com/B"]},
        "search_paths": {"a.com": ["https://a.com/search?q={mpn}"]},
        "learned_hosts": {"storefront": ["newdealer.example"]},
        "search_engine": "brave",
    }
    merged = merge_memory(base, overlay)
    assert merged["known_urls"]["A"] == ["https://a.com/A"]
    assert merged["known_urls"]["B"] == ["https://b.com/B"]
    assert "https://a.com/p/{mpn}" in merged["search_paths"]["a.com"]
    assert "https://a.com/search?q={mpn}" in merged["search_paths"]["a.com"]
    assert merged["learned_hosts"]["storefront"] == ["newdealer.example"]
    assert merged["search_engine"] == "brave"


def test_unconfigured_store_is_noop(monkeypatch):
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    assert configured() is False
    assert load_shared() is None
    assert save_shared({"known_urls": {}}) is False


def test_persist_shared_without_store_returns_snapshot():
    memory = persist_shared(
        {
            "known_urls": {"Z": ["https://z.com/Z"]},
            "search_paths": {},
            "dead_paths": {},
            "search_engine": None,
        }
    )
    assert memory["known_urls"]["Z"] == ["https://z.com/Z"]
