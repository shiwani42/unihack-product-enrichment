from extract.evidence import EvidenceBundle


def test_wikidata_official_website_keeps_company_host(monkeypatch):
    monkeypatch.setenv("UNILOG_WIKIDATA", "1")
    from sources import wikidata

    wikidata._cache.clear()

    def fake_json(params):
        if params.get("action") == "wbsearchentities":
            return {
                "search": [
                    {
                        "id": "Q1",
                        "label": "SawStop",
                        "description": "American table saw manufacturer",
                    }
                ]
            }
        return {
            "entities": {
                "Q1": {
                    "descriptions": {"en": {"value": "American table saw manufacturer"}},
                    "claims": {
                        "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q783794"}}}}],
                        "P856": [{"mainsnak": {"datavalue": {"value": "https://www.sawstop.com/"}}}],
                    },
                }
            }
        }

    monkeypatch.setattr(wikidata, "_get_json", fake_json)
    assert wikidata.official_website_hosts(["Saw Stop LLC"]) == ["sawstop.com"]
    assert wikidata.official_website_hosts(["Saw Stop LLC"]) == ["sawstop.com"]


def test_wikidata_skips_humans_and_shopping_hosts(monkeypatch):
    monkeypatch.setenv("UNILOG_WIKIDATA", "1")
    from sources import wikidata

    wikidata._cache.clear()

    def fake_json(params):
        if params.get("action") == "wbsearchentities":
            return {"search": [{"id": "Q5", "label": "Prime", "description": "human"}]}
        return {
            "entities": {
                "Q5": {
                    "descriptions": {"en": {"value": "human"}},
                    "claims": {
                        "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
                        "P856": [{"mainsnak": {"datavalue": {"value": "https://www.amazon.com/"}}}],
                    },
                }
            }
        }

    monkeypatch.setattr(wikidata, "_get_json", fake_json)
    assert wikidata.official_website_hosts(["Prime"]) == []


def test_wikidata_disabled_returns_nothing(monkeypatch):
    monkeypatch.setenv("UNILOG_WIKIDATA", "0")
    from sources.wikidata import official_website_hosts

    assert official_website_hosts(["SawStop"]) == []


def test_unmapped_fetch_uses_wikidata_host(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    monkeypatch.setenv("UNILOG_WIKIDATA", "1")
    monkeypatch.setattr("sources.live_enrich.official_website_hosts", lambda names: ["sawstop.com"])
    rich = (
        "<html><body>Voltage Rating 120 Color Black "
        "Material Steel Amperage Rating 15</body></html>"
    )
    requested = []

    async def fake_pages(urls, timeout=None):
        requested.extend(urls)
        pages = []
        for url in urls:
            html = rich if "sawstop.com" in url else ""
            pages.append((200, html, url, url) if html else (0, "", url, url))
        return pages

    monkeypatch.setattr("sources.live_enrich.fetch_all_pages", fake_pages)
    monkeypatch.setattr("sources.live_enrich.fetch_pdf_evidence", lambda urls: EvidenceBundle())
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence(
        "TGP2-FA",
        [],
        fetch_pdfs=False,
        manufacturer_name="Saw Stop LLC",
        brand_name="SawStop",
    )
    assert any("sawstop.com" in url for url in requested)
    assert "sawstop.com" in (bundle.mfr_url or "")
    assert len(bundle.items) >= 2
