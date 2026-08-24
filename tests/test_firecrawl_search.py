import asyncio

from sources.firecrawl_search import parse_firecrawl_urls


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


def test_firecrawl_engine_preferred_when_it_returns_mpn_hits(monkeypatch):
    from sources.web_search import collect_search_result_urls, last_search_engine

    monkeypatch.setenv("UNILOG_FIRECRAWL", "1")

    async def fake_firecrawl(query, limit=8):
        return ["https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF"]

    async def fake_engine(client, engine, query):
        return 200, '<html><a href="https://www.bosch-home.com/us/product/SHPM78Z55N">Bosch</a></html>'

    monkeypatch.setattr("sources.web_search.firecrawl_search_urls", fake_firecrawl)
    monkeypatch.setattr("sources.web_search.firecrawl_enabled", lambda: True)
    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert urls == ["https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF"]
    assert last_search_engine() == "firecrawl"


def test_firecrawl_miss_falls_through_to_html_engines(monkeypatch):
    from sources.web_search import collect_search_result_urls, last_search_engine

    monkeypatch.setenv("UNILOG_FIRECRAWL", "1")

    async def fake_firecrawl(query, limit=8):
        return []

    async def fake_engine(client, engine, query):
        if engine == "brave":
            return 200, '<html><a href="https://www.frigidaire.com/p/PDSH4816AF">Frigidaire</a></html>'
        return 403, "no"

    monkeypatch.setattr("sources.web_search.firecrawl_search_urls", fake_firecrawl)
    monkeypatch.setattr("sources.web_search.firecrawl_enabled", lambda: True)
    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert urls == ["https://www.frigidaire.com/p/PDSH4816AF"]
    assert last_search_engine() == "brave"


def test_firecrawl_disabled_skips_api(monkeypatch):
    from sources.web_search import collect_search_result_urls, engine_order

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
