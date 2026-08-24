import asyncio
import os

from sources.firecrawl_search import (
    firecrawl_circuit_open,
    firecrawl_enabled,
    parse_firecrawl_urls,
    reset_firecrawl_circuit,
)


def test_parse_firecrawl_v2_web_payload():
    payload = {
        "success": True,
        "data": {
            "web": [
                {
                    "url": "https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF",
                    "title": "Frigidaire PDSH4816AF",
                    "description": "Product support",
                    "position": 1,
                },
                {
                    "url": "https://www.amazon.com/dp/PDSH4816AF",
                    "title": "Amazon",
                    "position": 2,
                },
            ]
        },
    }
    urls = parse_firecrawl_urls(payload)
    assert urls[0].endswith("PDSH4816AF")
    assert "amazon.com" in urls[1]


def test_parse_firecrawl_empty_or_error():
    assert parse_firecrawl_urls({"success": False, "error": "rate"}) == []
    assert parse_firecrawl_urls({}) == []
    assert parse_firecrawl_urls(None) == []


def test_vercel_without_api_key_disables_firecrawl(monkeypatch):
    reset_firecrawl_circuit()
    monkeypatch.setenv("UNILOG_FIRECRAWL", "1")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_APIKEY", raising=False)
    assert firecrawl_enabled() is False


def test_vercel_with_api_key_enables_firecrawl(monkeypatch):
    reset_firecrawl_circuit()
    monkeypatch.setenv("UNILOG_FIRECRAWL", "1")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    assert firecrawl_enabled() is True


def test_firecrawl_engine_preferred_when_keyed_and_hits(monkeypatch):
    from sources.web_search import collect_search_result_urls, last_search_engine

    reset_firecrawl_circuit()
    monkeypatch.setenv("UNILOG_FIRECRAWL", "1")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.delenv("VERCEL", raising=False)

    async def fake_firecrawl(query, limit=8):
        return ["https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF"]

    async def fake_engine(client, engine, query):
        return 200, '<html><a href="https://www.bosch-home.com/us/product/SHPM78Z55N">Bosch</a></html>'

    monkeypatch.setattr("sources.web_search.firecrawl_search_urls", fake_firecrawl)
    monkeypatch.setattr("sources.web_search.firecrawl_enabled", lambda: True)
    monkeypatch.setattr("sources.web_search.firecrawl_has_api_key", lambda: True)
    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert urls == ["https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF"]
    assert last_search_engine() == "firecrawl"


def test_firecrawl_miss_falls_through_to_html_engines(monkeypatch):
    from sources.web_search import collect_search_result_urls, last_search_engine

    reset_firecrawl_circuit()
    monkeypatch.setenv("UNILOG_FIRECRAWL", "1")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)

    async def fake_firecrawl(query, limit=8):
        return []

    async def fake_engine(client, engine, query):
        if engine == "brave":
            return 200, '<html><a href="https://www.frigidaire.com/p/PDSH4816AF">Frigidaire</a></html>'
        return 403, "no"

    monkeypatch.setattr("sources.web_search.firecrawl_search_urls", fake_firecrawl)
    monkeypatch.setattr("sources.web_search.firecrawl_enabled", lambda: True)
    monkeypatch.setattr("sources.web_search.firecrawl_has_api_key", lambda: False)
    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert urls == ["https://www.frigidaire.com/p/PDSH4816AF"]
    assert last_search_engine() == "brave"


def test_firecrawl_circuit_trips_on_api_reject(monkeypatch):
    import httpx

    from sources import firecrawl_search as fc

    reset_firecrawl_circuit()
    monkeypatch.setenv("UNILOG_FIRECRAWL", "1")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    class _Resp:
        status_code = 200

        def json(self):
            return {"success": False, "error": "suspicious IP"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr(fc.httpx, "AsyncClient", lambda **kwargs: _Client())
    urls = asyncio.run(fc.firecrawl_search_urls("PDSH4816AF"))
    assert urls == []
    assert firecrawl_circuit_open() is True
    assert firecrawl_enabled() is False


def test_firecrawl_disabled_skips_api(monkeypatch):
    from sources.web_search import collect_search_result_urls, engine_order

    reset_firecrawl_circuit()
    monkeypatch.setenv("UNILOG_FIRECRAWL", "0")
    monkeypatch.setattr("sources.web_search.firecrawl_enabled", lambda: False)
    assert "firecrawl" not in engine_order()

    called = {"n": 0}

    async def fake_firecrawl(query, limit=8):
        called["n"] += 1
        return ["https://www.frigidaire.com/p/PDSH4816AF"]

    async def fake_engine(client, engine, query):
        return 200, '<html><a href="https://www.frigidaire.com/p/PDSH4816AF">x</a></html>'

    monkeypatch.setattr("sources.web_search.firecrawl_search_urls", fake_firecrawl)
    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert called["n"] == 0
    assert urls == ["https://www.frigidaire.com/p/PDSH4816AF"]
