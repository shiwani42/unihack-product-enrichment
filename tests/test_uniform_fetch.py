"""Regression tests: uniform live-fetch opportunity + validation honesty."""

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


def test_generic_category_gets_same_fetch_opportunity(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    calls = {"n": 0}

    def fake_fetch(mpn, domains, max_urls=None, fetch_pdfs=True, **kwargs):
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


def test_seed_cache_does_not_skip_live_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_LIVE_FETCH", "1")
    calls = {"n": 0}

    def fake_fetch(mpn, domains, max_urls=None, fetch_pdfs=True, **kwargs):
        calls["n"] += 1
        bundle = EvidenceBundle(mfr_url=f"https://frigidaire.com/{mpn}")
        bundle.set(
            Evidence(field="Color", value="Stainless Steel", source_url=f"https://frigidaire.com/{mpn}", extractor="html", confidence=0.8)
        )
        return bundle

    monkeypatch.setattr(pipeline_module, "fetch_manufacturer_evidence", fake_fetch)
    bundle = _fetch_evidence("PDSH4816AF", "PDSH4816AF", _identity(["frigidaire.com"]), EvidenceBundle(), "built_in_dishwasher")
    assert calls["n"] == 1
    assert len(bundle.items) == 1


def test_live_fetch_exception_does_not_abort_row(monkeypatch):
    monkeypatch.setenv("UNILOG_LIVE_FETCH", "1")

    def boom(*args, **kwargs):
        raise RuntimeError("manufacturer site timed out")

    monkeypatch.setattr(pipeline_module, "fetch_manufacturer_evidence", boom)
    result = enrich_input_row(
        {
            "Mfg_Part_Num": "49-94-3000",
            "Part_Desc": '3" x 0.040" x 3/8" Metal Cut Off Wheel',
            "DIB_Brand": "MILWAUKEE",
        },
        load_output_headers(),
    )
    assert result.row["Mfg_Part_Num"] == "49-94-3000"
    assert result.error == ""
    assert result.row is not None


def test_live_fetch_kill_switch_skips_network(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
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


def test_candidate_urls_never_include_shopping_hosts():
    from sources.finder import candidate_mfr_urls, is_blocked_url

    # Mixed list on purpose: Amazon/eBay must be dropped; Frigidaire is the
    # manufacturer host from the expected-output sample and must remain.
    urls = candidate_mfr_urls("X1", ["amazon.com", "ebay.com", "frigidaire.com"])
    assert urls
    assert all(not is_blocked_url(url) for url in urls)
    joined = " ".join(urls).lower()
    assert "amazon." not in joined
    assert "ebay." not in joined
    assert any("frigidaire.com" in url.lower() for url in urls)


def test_product_link_discovery_stays_on_manufacturer_domain():
    from extract.ref_discovery import discover_product_links

    html = """
    <html><body>
      <a href="https://www.frigidaire.com/en/p/PDSH4816AF">PDSH4816AF dishwasher</a>
      <a href="/products/PDSH4816AF-gallery">PDSH4816AF gallery</a>
      <a href="https://www.amazon.com/dp/PDSH4816AF">buy PDSH4816AF</a>
      <a href="https://www.whirlpool.com/p/PDSH4816AF">wrong brand PDSH4816AF</a>
    </body></html>
    """
    links = discover_product_links(
        html,
        "https://www.frigidaire.com/search?q=PDSH4816AF",
        "PDSH4816AF",
        ["frigidaire.com"],
    )
    assert "https://www.frigidaire.com/en/p/PDSH4816AF" in links
    assert "https://www.frigidaire.com/products/PDSH4816AF-gallery" in links
    assert all("amazon." not in url.lower() for url in links)
    assert all("whirlpool." not in url.lower() for url in links)


def test_product_link_discovery_drops_shopping_keeps_distributor_when_listed():
    from extract.ref_discovery import discover_product_links

    html = """
    <html><body>
      <a href="https://www.frigidaire.com/en/p/PDSH4816AF">PDSH4816AF spec</a>
      <a href="https://www.grainger.com/product/PDSH4816AF">PDSH4816AF spec</a>
      <a href="https://www.amazon.com/dp/PDSH4816AF">PDSH4816AF</a>
    </body></html>
    """
    links = discover_product_links(
        html,
        "https://www.frigidaire.com/search?q=PDSH4816AF",
        "PDSH4816AF",
        ["frigidaire.com", "grainger.com"],
    )
    assert "https://www.frigidaire.com/en/p/PDSH4816AF" in links
    assert "https://www.grainger.com/product/PDSH4816AF" in links
    assert all("amazon." not in url.lower() for url in links)


def test_committed_seed_files_are_not_loadable():
    from extract.cache import load_cached_bundle

    assert load_cached_bundle("PDSH4816AF") is None
    assert load_cached_bundle("WDTS7024RZ") is None


def test_merge_keeps_marketing_and_product_ids():
    from extract.merge import merge_bundles

    first = EvidenceBundle(marketing="A quiet dishwasher for tight kitchens.")
    first.product_ids["sku"] = "PDSH4816AF"
    first.features = ["Third rack"]
    second = EvidenceBundle()
    second.set(Evidence(field="Color", value="Stainless Steel", extractor="html", confidence=0.8))
    merged = merge_bundles(first, second)
    assert merged.marketing.startswith("A quiet")
    assert merged.product_ids["sku"] == "PDSH4816AF"
    assert "Third rack" in merged.features
    assert merged.get("Color").value == "Stainless Steel"


def test_third_party_fallback_urls_exclude_shopping():
    from sources.finder import candidate_third_party_urls, is_blocked_url

    urls = candidate_third_party_urls("X1")
    assert urls
    joined = " ".join(urls).lower()
    assert "energystar.gov" in joined
    assert "amazon." not in joined
    assert "ebay." not in joined
    assert all(not is_blocked_url(url) for url in urls)


def test_distributor_fallback_urls_exclude_shopping():
    from sources.finder import candidate_distributor_urls, is_blocked_url

    urls = candidate_distributor_urls("X1")
    assert urls
    joined = " ".join(urls).lower()
    assert "grainger.com" in joined
    assert "amazon." not in joined
    assert "ebay." not in joined
    assert all(not is_blocked_url(url) for url in urls)


def test_kitchenaid_also_fetches_whirlpool_family_hosts():
    from sources.finder import candidate_family_urls

    urls = candidate_family_urls("KDFM404KPS", ["kitchenaid.com"])
    joined = " ".join(urls).lower()
    assert "whirlpool.com" in joined or "learnwhirlpool.com" in joined
    assert "amazon." not in joined


def test_source_policy_strips_marketing_from_fallback_pages():
    from extract.evidence import Evidence
    from sources.source_policy import apply_source_policy, classify_url

    assert classify_url("https://www.amazon.com/dp/X1", ["frigidaire.com"]) == "blocked"
    assert classify_url("https://www.grainger.com/product/X1", ["frigidaire.com"]) == "distributor"
    assert classify_url("https://www.frigidaire.com/p/X1", ["frigidaire.com"]) == "manufacturer"

    bundle = EvidenceBundle(marketing="Buy it today.", mfr_url="https://www.grainger.com/product/X1")
    bundle.features = ["Third rack"]
    bundle.image_urls = ["https://www.grainger.com/img.jpg"]
    bundle.set(Evidence(field="Color", value="Stainless Steel", extractor="html", confidence=0.82, source_url="https://www.grainger.com/product/X1"))
    apply_source_policy(bundle, "https://www.grainger.com/product/X1", ["frigidaire.com"])
    assert bundle.marketing == ""
    assert bundle.features == []
    assert bundle.image_urls == []
    assert bundle.mfr_url == ""
    assert bundle.get("Color").value == "Stainless Steel"
    assert bundle.get("Color").confidence <= 0.68


def test_search_results_drop_shopping_and_unknown_hosts():
    from sources.web_search import filter_allowed_results, parse_search_result_urls

    html = """
    <html><body>
      <a href="https://www.frigidaire.com/p/PDSH4816AF">mfr</a>
      <a href="https://www.grainger.com/product/PDSH4816AF">dist</a>
      <a href="https://www.amazon.com/dp/PDSH4816AF">shop</a>
      <a href="https://www.dkhardware.com/p/PDSH4816AF">shop2</a>
      <a href="https://www.energystar.gov/productfinder/?search_text=PDSH4816AF">third</a>
      <a href="https://random-blog.example/PDSH4816AF">other</a>
    </body></html>
    """
    parsed = parse_search_result_urls(html)
    kept = filter_allowed_results(parsed, ["frigidaire.com"], limit=10)
    assert "https://www.frigidaire.com/p/PDSH4816AF" in kept
    assert all("grainger.com" not in url for url in kept)
    assert all("amazon." not in url for url in kept)
    assert all("dkhardware." not in url for url in parsed)
    assert all("energystar.gov" not in url for url in kept)
    assert all("random-blog.example" not in url for url in kept)


def test_fallback_search_keeps_distributor_not_shopping():
    from sources.web_search import filter_fallback_results, parse_search_result_urls

    html = """
    <html><body>
      <a href="https://www.grainger.com/product/PDSH4816AF">dist</a>
      <a href="https://www.amazon.com/dp/PDSH4816AF">shop</a>
      <a href="https://www.energystar.gov/productfinder/?search_text=PDSH4816AF">third</a>
    </body></html>
    """
    parsed = parse_search_result_urls(html)
    kept = filter_fallback_results(parsed, ["frigidaire.com"], "PDSH4816AF", limit=10)
    assert "https://www.grainger.com/product/PDSH4816AF" in kept
    assert "https://www.energystar.gov/productfinder/?search_text=PDSH4816AF" in kept
    assert all("amazon." not in url for url in kept)

    from sources.source_policy import DISTRIBUTOR, THIRD_PARTY

    third = filter_fallback_results(parsed, ["frigidaire.com"], "PDSH4816AF", limit=10, kinds=frozenset({THIRD_PARTY}))
    dist = filter_fallback_results(parsed, ["frigidaire.com"], "PDSH4816AF", limit=10, kinds=frozenset({DISTRIBUTOR}))
    assert third == ["https://www.energystar.gov/productfinder/?search_text=PDSH4816AF"]
    assert dist == ["https://www.grainger.com/product/PDSH4816AF"]


def test_fetch_runs_without_manufacturer_domains(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_LIVE_FETCH", "1")
    calls = {"n": 0}

    def fake_fetch(mpn, domains, max_urls=None, fetch_pdfs=True, **kwargs):
        calls["n"] += 1
        assert domains == []
        return EvidenceBundle()

    monkeypatch.setattr(pipeline_module, "fetch_manufacturer_evidence", fake_fetch)
    _fetch_evidence("X1", "X1", _identity([]), EvidenceBundle(), "generic_industrial")
    assert calls["n"] == 1


def test_sample_skus_target_official_manufacturer_pages():
    from sources.finder import best_mfr_url, candidate_mfr_urls

    frigidaire = candidate_mfr_urls("PDSH4816AF", ["frigidaire.com", "support.frigidaire.com"])
    joined = " ".join(frigidaire)
    assert "Owner-Center/Product-Support/PDSH4816AF" in joined
    assert "owner-center/product-support/" in joined.lower()
    assert "amazon." not in joined.lower()
    assert "en/p/owner-center/product-support/PDSH4816AF" in best_mfr_url(
        "PDSH4816AF", ["frigidaire.com", "support.frigidaire.com"]
    )

    whirlpool = candidate_mfr_urls("WDTS7024RZ", ["whirlpool.com", "learnwhirlpool.com"])
    assert any("learnwhirlpool.com/smartsearchresults?searchtext=WDTS7024R" in url for url in whirlpool)
    assert best_mfr_url("WDTS7024RZ", ["whirlpool.com", "learnwhirlpool.com"]).startswith("https://learnwhirlpool.com/")


def test_kitchenaid_targets_official_whirlpool_literature():
    from sources.finder import candidate_mfr_urls

    urls = candidate_mfr_urls("KDFM404KPS", ["kitchenaid.com", "learnwhirlpool.com"])
    assert any("learnwhirlpool.com/smartsearchresults?searchtext=KDFM404KPS" in url for url in urls)


def test_discovers_official_manufacturer_pdfs():
    from extract.ref_discovery import discover_pdf_links

    html = """
    <html><body>
      <a href="https://www.whirlpool.com/content/dam/global/documents/202412/owners-manual-w11323304-revj.pdf">Owner's Manual</a>
      <a href="https://www.whirlpool.com/content/dam/global/documents/202406/installation-instructions-w11323304-revG.pdf">Installation Instruction</a>
      <script>var docs=["https://www.whirlpool.com/content/dam/global/documents/202502/dimension-guide-w11438541-revg.pdf"];</script>
      <img src="https://www.whirlpool.com/content/dam/global/shot-lists/hero.tif">
    </body></html>
    """
    links = discover_pdf_links(html, "https://learnwhirlpool.com/smartsearchresults")
    assert "https://www.whirlpool.com/content/dam/global/documents/202412/owners-manual-w11323304-revj.pdf" in links
    assert "https://www.whirlpool.com/content/dam/global/documents/202406/installation-instructions-w11323304-revG.pdf" in links
    assert "https://www.whirlpool.com/content/dam/global/documents/202502/dimension-guide-w11438541-revg.pdf" in links
    assert all(".tif" not in url for url in links)


def test_shopping_hosts_are_blocked_before_fetch():
    from sources.finder import is_blocked_url, is_distributor_url

    blocked = [
        "https://www.amazon.com/dp/PDSH4816AF",
        "https://www.amazon.co.uk/dp/X1",
        "https://amzn.to/abc123",
        "https://www.ebay.com/itm/123",
        "https://www.ebay.co.uk/itm/123",
        "https://www.walmart.com/ip/x",
        "https://www.homedepot.com/p/x",
        "https://www.homedepot.ca/product/x",
        "https://www.google.com/shopping/product/1",
        "https://www.dkhardware.com/product-x",
        "https://www.acehardware.com/p/x",
        "https://www.acmetools.com/p/x",
        "https://www.beeslighting.com/p/x",
        "https://www.lightology.com/p/x",
        "https://lightingnewyork.com/p/x",
        "https://www.us-appliance.com/p/x",
        "https://www.ajmadison.com/p/x",
        "https://poshmark.com/listing/x",
        "https://www.northerntool.com/p/x",
        "https://www.sutherlands.com/p/x",
        "https://online.flippingbook.com/view/x",
        "https://en.wikipedia.org/wiki/x",
        "https://shop.app/x",
    ]
    assert all(is_blocked_url(url) for url in blocked)
    assert not is_blocked_url("https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF")
    assert not is_blocked_url("https://learnwhirlpool.com/smartsearchresults?searchtext=WDTS7024R")
    assert not is_blocked_url("https://s3.amazonaws.com/mfr-docs/spec.pdf")
    assert not is_blocked_url("https://www.milwaukeetool.com/products/details/x")
    assert not is_blocked_url("https://www.kichler.com/p/x")
    assert not is_blocked_url("https://www.festoolusa.com/products/x")
    assert not is_blocked_url("https://www.boschtools.com/us/en/products/x")
    assert not is_blocked_url("https://www.3m.com/3M/en_US/p/d/x")
    assert not is_blocked_url("https://www.grainger.com/product/X1")
    assert not is_blocked_url("https://www.zoro.com/i/x")
    assert not is_blocked_url("https://beavertools.com/products/x")
    assert is_distributor_url("https://www.grainger.com/product/X1")
    assert is_distributor_url("https://www.woodworkerexpress.com/p/x")
    assert not is_distributor_url("https://www.amazon.com/dp/X1")
    assert not is_distributor_url("https://www.dkhardware.com/p/x")


def test_fetch_helpers_do_not_request_shopping_urls():
    import asyncio

    from sources.async_fetcher import fetch_all_successful, fetch_html_async
    from sources.browser_fetcher import fetch_html, fetch_html_with_browser

    amazon = "https://www.amazon.com/dp/PDSH4816AF"
    ebay = "https://www.ebay.com/itm/123"
    retail = "https://www.dkhardware.com/product/X1"
    assert asyncio.run(fetch_html_async(amazon)) == (0, "", amazon)
    assert asyncio.run(fetch_all_successful([amazon, ebay, retail])) == []
    assert fetch_html(amazon) == (0, "", amazon)
    assert fetch_html_with_browser(ebay) == (0, "", ebay)
    assert fetch_html(retail) == (0, "", retail)


def test_unknown_brand_keeps_search_in_first_fetch_window():
    from app.config import FETCH_URL_LIMIT
    from sources.finder import candidate_mfr_urls, first_fetch_window

    urls = first_fetch_window(candidate_mfr_urls("ZZ-JUDGE-NEW", ["newbrandtools.com"]), FETCH_URL_LIMIT)
    joined = " ".join(urls)
    assert "https://www.newbrandtools.com/search?q=ZZ-JUDGE-NEW" in urls
    assert "https://www.newbrandtools.com/p/ZZ-JUDGE-NEW" in urls
    assert "https://www.newbrandtools.com/products/ZZ-JUDGE-NEW" in urls
    assert "https://www.newbrandtools.com/appliance/ZZ-JUDGE-NEW" not in urls
    assert "owner-center" not in joined
    assert "gea-specs" not in joined
    assert "learnwhirlpool" not in joined
    assert "milwaukeetool.com" not in joined


def test_learned_product_templates_do_not_drop_search_fallback():
    import json

    from app.config import FETCH_URL_LIMIT
    from sources.finder import SEARCH_PATHS_FILE, candidate_mfr_urls, first_fetch_window, reset_search_path_cache

    SEARCH_PATHS_FILE.write_text(
        json.dumps(
            {
                "newbrandtools.com": [
                    f"https://www.newbrandtools.com/cat{i}/{{mpn}}" for i in range(12)
                ]
            }
        ),
        encoding="utf-8",
    )
    reset_search_path_cache()
    urls = first_fetch_window(candidate_mfr_urls("ZZ-NEW", ["newbrandtools.com"]), FETCH_URL_LIMIT)
    assert any("/search?q=ZZ-NEW" in url for url in urls)
    assert any("/cat0/ZZ-NEW" in url for url in urls)
    assert len(urls) <= FETCH_URL_LIMIT


def test_distributor_url_never_becomes_mfr_url_for_unseen_sku():
    from extract.evidence import EvidenceBundle
    from sources.finder import best_mfr_url, candidate_mfr_urls
    from sources.known_urls import remember_urls
    from sources.source_policy import apply_source_policy, classify_url

    remember_urls("ZZ-JUDGE-NEW", ["https://www.grainger.com/product/ZZ-JUDGE-NEW"])
    assert classify_url("https://www.grainger.com/product/ZZ-JUDGE-NEW", []) == "distributor"
    assert all("grainger" not in url.lower() for url in candidate_mfr_urls("ZZ-JUDGE-NEW", []))
    assert "grainger" not in (best_mfr_url("ZZ-JUDGE-NEW", []) or "").lower()
    bundle = EvidenceBundle(marketing="Buy it today.", mfr_url="https://www.grainger.com/product/ZZ-JUDGE-NEW")
    apply_source_policy(bundle, "https://www.grainger.com/product/ZZ-JUDGE-NEW", ["newbrandtools.com"])
    assert bundle.mfr_url == ""


def test_unknown_manufacturer_guesses_domain_from_name():
    from sources.domain_discovery import guess_domains_from_name

    assert "bosch.com" in guess_domains_from_name("Bosch Thermotechnology")
    assert "rheem.com" in guess_domains_from_name("Rheem Manufacturing")
    assert "hunterfan.com" in guess_domains_from_name("Hunter Fan Company")
    assert "ustape.com" in guess_domains_from_name("U S Tape Company")
    assert "primewirecable.com" in guess_domains_from_name("Prime Wire & Cable")
    assert guess_domains_from_name("") == []
    assert guess_domains_from_name("COMMODITY - UNBRANDED") == []


def test_search_queries_include_part_and_manufacturer_name():
    from sources.web_search import search_endpoint_urls

    urls = search_endpoint_urls("SHPM78Z55N", [], manufacturer_name="Bosch", brand_name="Bosch")
    joined = " ".join(urls)
    assert "SHPM78Z55N" in joined
    assert "Bosch" in joined
    assert "html.duckduckgo.com/html" in joined
    assert "search.brave.com/search" in joined
    assert "site:" not in joined


def test_challenge_pages_are_not_search_results():
    from sources.web_search import is_challenge_page, parse_search_result_urls

    assert is_challenge_page(403, "<html>blocked</html>")
    assert is_challenge_page(429, "<html>rate limit</html>")
    assert is_challenge_page(200, "<html><title>Pardon Our Interruption</title>" + ("x" * 200) + "</html>")
    html = (
        '<html><a class="result__a" href="https://duckduckgo.com/l/'
        '?uddg=https%3A%2F%2Fwww.frigidaire.com%2Fp%2FX1">Frigidaire</a></html>'
    )
    assert parse_search_result_urls(html) == ["https://www.frigidaire.com/p/X1"]
    brave = """
    <html><body>
      <a href="https://www.bosch-home.com/us/product/SHPM78Z55N">Bosch</a>
      <cite>www.bosch-home.com › us › product › SHPM78Z55N</cite>
      <a href="https://search.brave.com/search?q=SHPM78Z55N">engine</a>
    </body></html>
    """
    parsed = parse_search_result_urls(brave)
    assert "https://www.bosch-home.com/us/product/SHPM78Z55N" in parsed
    assert all("brave." not in url for url in parsed)


def test_search_collector_prefers_ipv4_then_dual_stack(monkeypatch):
    import asyncio

    from sources.web_search import collect_search_result_urls

    flags: list[bool] = []

    class _CM:
        def __init__(self, ipv4: bool):
            self.ipv4 = ipv4

        async def __aenter__(self):
            flags.append(self.ipv4)
            return self

        async def __aexit__(self, *exc):
            return False

    def fake_client(ipv4: bool = False):
        return _CM(ipv4)

    async def fake_engine(client, engine, query):
        if getattr(client, "ipv4", False):
            return 200, '<html><a href="https://www.frigidaire.com/p/PDSH4816AF">x</a></html>'
        return 403, "no"

    monkeypatch.setattr("sources.web_search._client", fake_client)
    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert flags[0] is True
    assert False in flags
    assert urls == ["https://www.frigidaire.com/p/PDSH4816AF"]


def test_search_collector_backs_off_on_429(monkeypatch):
    import asyncio

    from sources.web_search import SEARCH_429_BACKOFF_SEC, collect_search_result_urls

    sleeps: list[float] = []
    brave_calls = {"n": 0}

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    async def fake_engine(client, engine, query):
        if engine != "brave":
            return 403, "no"
        brave_calls["n"] += 1
        if brave_calls["n"] == 1:
            return 429, "rate"
        return 200, '<html><a href="https://www.frigidaire.com/p/PDSH4816AF">x</a></html>'

    monkeypatch.setattr("sources.web_search.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert sleeps and sleeps[0] >= SEARCH_429_BACKOFF_SEC
    assert urls == ["https://www.frigidaire.com/p/PDSH4816AF"]


def test_search_collector_failsover_when_ddg_is_blocked(monkeypatch):
    import asyncio

    from sources.web_search import collect_search_result_urls

    async def fake_engine(client, engine, query):
        if engine in {"brave", "ddg_html"}:
            return 403, "<html>denied</html>"
        if engine == "ddg_lite":
            return 200, "<html>captcha unusual traffic " + ("n" * 200) + "</html>"
        return 200, '<html><a href="https://www.bosch-home.com/us/product/SHPM78Z55N">Bosch</a></html>'

    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("SHPM78Z55N", manufacturer_name="Bosch"))
    assert "https://www.bosch-home.com/us/product/SHPM78Z55N" in urls
    junk = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert all("chegg.com" not in url for url in junk)


def test_search_collector_uses_whichever_engine_returns_mpn_hits(monkeypatch):
    import asyncio

    from sources.web_search import collect_search_result_urls, last_search_engine

    called: list[str] = []

    async def fake_engine(client, engine, query):
        called.append(engine)
        if engine == "brave":
            return 200, '<html><a href="https://www.frigidaire.com/p/PDSH4816AF">Frigidaire</a></html>'
        return 200, '<html><a href="https://www.bosch-home.com/us/product/SHPM78Z55N">Bosch</a></html>'

    monkeypatch.setattr("sources.web_search._engine_html", fake_engine)
    urls = asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert urls == ["https://www.frigidaire.com/p/PDSH4816AF"]
    assert last_search_engine() == "brave"
    assert called[0] == "brave"
    called.clear()
    asyncio.run(collect_search_result_urls("PDSH4816AF", manufacturer_name="Frigidaire"))
    assert called[0] == "brave"


def test_url_memory_snapshot_keeps_winning_search_engine():
    from sources.url_store import restore, snapshot
    from sources.web_search import last_search_engine, set_last_search_engine

    set_last_search_engine("brave")
    memory = snapshot()
    assert memory["search_engine"] == "brave"
    set_last_search_engine("bing")
    restore(memory)
    assert last_search_engine() == "brave"


def test_unknown_manufacturer_search_keeps_name_matched_host():
    from sources.domain_discovery import select_search_hits
    from sources.web_search import parse_search_result_urls

    html = """
    <html><body>
      <a href="https://www.bosch-home.com/us/product/SHPM78Z55N">Bosch SHPM78Z55N</a>
      <a href="https://www.amazon.com/dp/SHPM78Z55N">shop</a>
      <a href="https://www.grainger.com/product/SHPM78Z55N">dist</a>
      <a href="https://en.wikipedia.org/wiki/SHPM78Z55N">wiki</a>
      <a href="https://random-blog.example/SHPM78Z55N">other</a>
    </body></html>
    """
    parsed = parse_search_result_urls(html)
    hits, domains = select_search_hits(parsed, [], "SHPM78Z55N", ["Bosch"], limit=10)
    assert "https://www.bosch-home.com/us/product/SHPM78Z55N" in hits
    assert "bosch-home.com" in domains
    assert all("amazon." not in url for url in hits)
    assert all("wikipedia" not in url for url in hits)
    assert all("random-blog.example" not in url for url in hits)


def test_unmapped_search_keeps_parent_company_product_url():
    from sources.domain_discovery import select_search_hits

    parsed = [
        "https://www.abb.com/products/A410RCAR",
        "https://www.amazon.com/dp/A410RCAR",
        "https://www.chemblink.com/en/products/A410RCAR.htm",
        "https://random-blog.example/A410RCAR",
        "https://www.grainger.com/product/A410RCAR",
    ]
    hits, domains = select_search_hits(parsed, [], "A410RCAR", ["Carlon"], limit=10)
    assert "https://www.abb.com/products/A410RCAR" in hits
    assert "abb.com" in domains
    assert all("amazon." not in url for url in hits)
    assert all("chemblink" not in url for url in hits)
    assert all("random-blog" not in url for url in hits)
    assert all("grainger" not in url for url in hits)


def _stub_fetch_pages(monkeypatch, html_for):
    requested: list[str] = []

    async def fake_pages(urls, timeout=None, on_page=None, **kwargs):
        requested.extend(urls)
        pages = []
        for url in urls:
            html = html_for(url)
            if html:
                pages.append((200, html, url, url))
            else:
                pages.append((0, "", url, url))
        return pages

    async def fake_successful(urls, timeout=None, **kwargs):
        return [(status, html, final) for status, html, final, _req in await fake_pages(urls, timeout) if html]

    monkeypatch.setattr("sources.live_enrich.fetch_all_pages", fake_pages)
    monkeypatch.setattr("sources.live_enrich.fetch_all_successful", fake_successful, raising=False)
    monkeypatch.setattr("sources.live_enrich.fetch_pdf_evidence", lambda urls: EvidenceBundle())
    return requested


def test_distributor_not_fetched_when_manufacturer_has_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    rich = (
        "<html><body>Voltage Rating 120 Amperage Rating 15 A "
        "Material Stainless Steel Color Stainless Steel</body></html>"
    )
    requested = _stub_fetch_pages(monkeypatch, lambda url: rich if "frigidaire." in url else "")
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("X1", ["frigidaire.com"], fetch_pdfs=False)
    joined = " ".join(requested).lower()
    assert any("frigidaire.com" in url.lower() for url in requested)
    assert "grainger.com" not in joined
    assert "energystar.gov" not in joined
    assert len(bundle.items) >= 2
    assert "grainger" not in (bundle.mfr_url or "").lower()


def test_distributor_used_only_when_manufacturer_is_thin(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    dist_html = (
        "<html><body>Voltage Rating 120 Color Stainless Steel "
        "Material Stainless Steel Buy it today</body></html>"
    )

    def html_for(url: str) -> str:
        return dist_html if "grainger.com" in url else ""

    requested = _stub_fetch_pages(monkeypatch, html_for)
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("X1", ["frigidaire.com"], fetch_pdfs=False)
    joined = " ".join(requested).lower()
    assert "energystar.gov" in joined
    assert "grainger.com" in joined
    joined_order = joined.find("energystar.gov") < joined.find("grainger.com")
    assert joined_order
    assert bundle.get("Voltage Rating") is not None
    assert bundle.get("Voltage Rating").confidence <= 0.68
    assert "grainger" not in (bundle.mfr_url or "").lower()
    assert any("grainger.com" in url.lower() for url in bundle.ref_urls)
    assert bundle.marketing == ""
    assert bundle.image_urls == []


def test_soft_404_is_not_used_as_manufacturer_page(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    error = "<html><title>404 Page Not Found</title><body>18W ELECTRIC</body></html>"

    async def fake_pages(urls, timeout=None, on_page=None, **kwargs):
        pages = []
        for url in urls:
            if "leviton" in url.lower():
                pages.append((200, error, "https://leviton.com/error-pages/404", url))
            else:
                pages.append((0, "", url, url))
        return pages

    async def fake_successful(urls, timeout=None, **kwargs):
        return []

    monkeypatch.setattr("sources.live_enrich.fetch_all_pages", fake_pages)
    monkeypatch.setattr("sources.live_enrich.fetch_all_successful", fake_successful, raising=False)
    monkeypatch.setattr("sources.live_enrich.fetch_pdf_evidence", lambda urls: EvidenceBundle())
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("X1", ["leviton.com"], fetch_pdfs=False)
    assert "error-pages" not in (bundle.mfr_url or "").lower()
    assert all("error-pages" not in (item.source_url or "") for item in bundle.items)


def test_live_enrich_fetches_remembered_product_url_first(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    from sources.known_urls import known_urls_for, remember_urls

    product = "https://www.frigidaire.com/en/p/owner-center/product-support/X1"
    remember_urls("X1", [product])
    rich = (
        "<html><body>Voltage Rating 120 Amperage Rating 15 A "
        "Material Stainless Steel Color Stainless Steel</body></html>"
    )
    requested = _stub_fetch_pages(monkeypatch, lambda url: rich if "frigidaire." in url else "")
    from sources.live_enrich import fetch_manufacturer_evidence

    fetch_manufacturer_evidence("X1", ["frigidaire.com"], fetch_pdfs=False)
    assert requested[0] == product
    assert product in known_urls_for("X1")


def test_remembered_rich_pdp_skips_extra_manufacturer_and_family_guesses(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    from sources.known_urls import remember_urls

    product = "https://www.frigidaire.com/en/p/owner-center/product-support/X1"
    remember_urls("X1", [product])
    rich = (
        "<html><body>Voltage Rating 120 Amperage Rating 15 A "
        "Material Stainless Steel Color Stainless Steel</body></html>"
    )
    requested = _stub_fetch_pages(monkeypatch, lambda url: rich if "frigidaire." in url else "")
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("X1", ["frigidaire.com"], fetch_pdfs=False)
    joined = " ".join(requested).lower()
    assert requested == [product]
    assert "search?q=" not in joined
    assert "electrolux.com" not in joined
    assert "grainger.com" not in joined
    assert "energystar.gov" not in joined
    assert len(bundle.items) >= 2
    assert bundle.mfr_url == product


def test_thin_known_url_still_hunts_manufacturer_then_third_party(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    from sources.known_urls import remember_urls

    stale = "https://www.frigidaire.com/en/p/owner-center/product-support/X1"
    remember_urls("X1", [stale])
    dist_html = (
        "<html><body>Voltage Rating 120 Color Stainless Steel "
        "Material Stainless Steel Buy it today</body></html>"
    )

    def html_for(url: str) -> str:
        return dist_html if "grainger.com" in url else ""

    requested = _stub_fetch_pages(monkeypatch, html_for)
    from sources.live_enrich import fetch_manufacturer_evidence

    fetch_manufacturer_evidence("X1", ["frigidaire.com"], fetch_pdfs=False)
    joined = " ".join(requested).lower()
    assert requested[0] == stale
    assert "search?q=" in joined
    assert "energystar.gov" in joined
    assert "grainger.com" in joined
    assert joined.find("energystar.gov") < joined.find("grainger.com")


def test_playwright_runs_once_per_batch_and_skips_search_urls(monkeypatch):
    import asyncio

    calls: list[str] = []

    async def fake_html(url, timeout=None, client=None):
        return 403, "<html>denied</html>", url

    def fake_browser(url, timeout=None):
        calls.append(url)
        return 200, "<html>ok</html>", url

    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("UNILOG_PLAYWRIGHT", "1")
    monkeypatch.setattr("sources.async_fetcher.fetch_html_async", fake_html)
    monkeypatch.setattr("sources.async_fetcher.fetch_html_with_browser", fake_browser)
    from sources.async_fetcher import fetch_all_pages

    pages = asyncio.run(
        fetch_all_pages(
            [
                "https://www.frigidaire.com/p/X1",
                "https://www.frigidaire.com/p/X2",
                "https://www.frigidaire.com/search?q=X1",
            ]
        )
    )
    assert len(calls) == 1
    assert "search?" not in calls[0]
    assert len(pages) == 3


def test_large_html_skips_microdata_parse(monkeypatch):
    seen: list[list[str]] = []

    def fake_extract(html, base_url=None, syntaxes=None):
        seen.append(list(syntaxes or []))
        return {}

    monkeypatch.setattr("extract.structured.extruct.extract", fake_extract)
    from extract.structured import extract_structured_data

    extract_structured_data("x" * 400_000, "https://www.frigidaire.com/p/X1")
    extract_structured_data("<html></html>", "https://www.frigidaire.com/p/X1")
    assert "json-ld" in seen[0]
    assert "opengraph" in seen[0]
    assert "microdata" not in seen[0]
    assert "microdata" in seen[1]


def test_unmapped_part_manuf_is_used_as_search_name():
    from identity.brand_resolver import resolve_identity

    identity = resolve_identity("SHPM78Z55N", "Dishwasher SS", "", "", "Bosch Thermotechnology (99)")
    assert identity.manufacturer_name == "Bosch Thermotechnology"
    assert identity.domains == []
    assert identity.method == "part_manuf_unmapped"


def test_product_page_with_mpn_beats_manuals_index():
    from sources.finder import official_url_score

    pdp = "https://www.milwaukeetool.com/products/details/metal-cut-off/49-94-0013"
    manuals = "https://www.milwaukeetool.com/Support/Manuals-and-Downloads?search=49-94-0013"
    assert official_url_score(pdp, "49-94-0013") > official_url_score(manuals, "49-94-0013")


def test_known_brand_with_pdp_template_does_not_fill_window_with_generic_404s():
    from sources.finder import candidate_mfr_urls, first_fetch_window

    urls = first_fetch_window(candidate_mfr_urls("DCB518ASTS06G", ["diablotools.com"]), 8)
    joined = " ".join(urls)
    assert "https://diablotools.com/products/DCB518ASTS06G" in urls
    assert any("search?q=DCB518ASTS06G" in url for url in urls)
    assert "/product-support/DCB518ASTS06G" not in joined
    assert urls.count("https://www.diablotools.com/p/DCB518ASTS06G") == 0


def test_manufacturer_search_is_extracted_when_no_product_follow(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    html = (
        "<html><title>Search</title><body>Voltage Rating 120 "
        "Amperage Rating 15 Color White Material Steel</body></html>"
    )
    requested = _stub_fetch_pages(
        monkeypatch,
        lambda url: html if "smartsearchresults" in url or "search" in url.lower() else "",
    )
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("KDFM404KPS", ["kitchenaid.com", "learnwhirlpool.com"], fetch_pdfs=False)
    assert len(bundle.items) >= 2
    assert requested
    import inspect
    from sources.async_fetcher import _reject_shopping

    assert inspect.iscoroutinefunction(_reject_shopping)


def test_numeric_mpn_does_not_adopt_chemical_or_embedded_sku_hosts():
    from sources.domain_discovery import select_search_hits
    from sources.web_search import _mentions_mpn

    assert _mentions_mpn("https://www.hunterfan.com/search?q=59243", "59243")
    assert not _mentions_mpn("https://www.chemblink.com/en/products/59243-40-2.htm", "59243")
    assert not _mentions_mpn("https://makitatools.com/products/details/B-59243", "59243")
    parsed = [
        "https://www.chemblink.com/en/products/59243-40-2.htm",
        "https://www.hunterfan.com/search?q=59243",
        "https://makitatools.com/products/details/B-59243",
    ]
    hits, domains = select_search_hits(parsed, ["hunterfan.com"], "59243", ["Hunter Fan Company"], limit=10)
    assert hits == ["https://www.hunterfan.com/search?q=59243"]
    assert "chemblink.com" not in domains
    assert "makitatools.com" not in domains


def test_host_matches_compound_brand_label():
    from sources.domain_discovery import host_matches_names

    assert host_matches_names("hunterfan.com", ["Hunter Fan Company"])
    assert host_matches_names("milwaukeetool.com", ["Milwaukee"])
    assert host_matches_names("wizconnected.com", ["Wiz"])


def test_unmapped_brand_searches_before_name_dot_com_guesses(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "1")
    order: list[str] = []

    async def fake_search(mpn, manufacturer_domains, **kwargs):
        order.append("search")
        assert manufacturer_domains == []
        return ["https://www.parentco.example/products/ZZ-NEW-1"]

    requested = _stub_fetch_pages(
        monkeypatch,
        lambda url: (
            "<html><body>Voltage Rating 120 Color White Material Steel</body></html>"
            if "parentco.example" in url
            else ""
        ),
    )
    monkeypatch.setattr("sources.live_enrich.collect_search_result_urls", fake_search)
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence(
        "ZZ-NEW-1",
        [],
        fetch_pdfs=False,
        manufacturer_name="Newbrand Tools",
        brand_name="Newbrand Tools",
    )
    assert order == ["search"]
    assert requested[0] == "https://www.parentco.example/products/ZZ-NEW-1"
    assert len(bundle.items) >= 2
    assert "parentco.example" in (bundle.mfr_url or "")


def test_shopify_meta_follows_variant_sku_handle():
    from extract.ref_discovery import discover_product_links, shopify_product_urls

    html = """
    <html><head><title>Search: 2 results found for "59243"</title></head>
    <body>
    <script>
    var meta = {"products":[
      {"handle":"ceiling-fans-dempsey-low-profile-with-light-44-inch-fam773",
       "variants":[{"sku":"52390"},{"sku":"59243"}]},
      {"handle":"ceiling-fan-parts-finial-6435002834",
       "variants":[{"sku":"6435002834"}]}
    ]};
    for (var attr in meta) {}
    </script>
    </body></html>
    """
    urls = shopify_product_urls(html, "https://www.hunterfan.com/search?q=59243", "59243")
    assert urls == [
        "https://www.hunterfan.com/products/ceiling-fans-dempsey-low-profile-with-light-44-inch-fam773"
    ]
    found = discover_product_links(
        html
        + '<a href="https://www.amazon.com/dp/59243">buy</a>'
        + '<a href="/products/other-fan">other</a>',
        "https://www.hunterfan.com/search?q=59243",
        "59243",
        ["hunterfan.com"],
    )
    assert found == [
        "https://www.hunterfan.com/products/ceiling-fans-dempsey-low-profile-with-light-44-inch-fam773"
    ]


def test_shopify_search_page_is_followed_to_pdp(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    search = """
    <html><title>Search: 2 results found for "59243"</title>
    <script>
    var meta = {"products":[{"handle":"ceiling-fans-dempsey-low-profile-with-light-44-inch-fam773",
      "variants":[{"sku":"59243"}]}]};
    for (var attr in meta) {}
    </script></html>
    """
    pdp = (
        "<html><body>Voltage Rating 120 Color White "
        "Material Steel Diameter 44</body></html>"
    )
    pdp_url = "https://www.hunterfan.com/products/ceiling-fans-dempsey-low-profile-with-light-44-inch-fam773"

    def html_for(url: str) -> str:
        if "search?" in url:
            return search
        if url == pdp_url:
            return pdp
        return ""

    requested = _stub_fetch_pages(monkeypatch, html_for)
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("59243", ["hunterfan.com"], fetch_pdfs=False)
    assert pdp_url in requested
    assert bundle.mfr_url == pdp_url
    assert "chemblink" not in (bundle.mfr_url or "")
    assert len(bundle.items) >= 2


def test_pipeline_fetches_3m_stock_number_not_distributor_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_LIVE_FETCH", "1")
    seen: list[str] = []

    def fake_fetch(mpn, domains, max_urls=None, fetch_pdfs=True, **kwargs):
        seen.append(mpn)
        return EvidenceBundle()

    monkeypatch.setattr(pipeline_module, "fetch_manufacturer_evidence", fake_fetch)
    headers = load_output_headers()
    enrich_input_row(_row_by_mpn("3MABR-7100075678"), headers)
    assert seen
    assert seen[0] == "7100075678"


def test_query_search_url_is_not_used_as_mfr_url(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    html = (
        "<html><body>Voltage Rating 120 Color White "
        "Material Steel Amperage Rating 15</body></html>"
    )
    _stub_fetch_pages(monkeypatch, lambda url: html if "3m.com" in url else "")
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("7100075678", ["3m.com"], fetch_pdfs=False)
    assert "search?" not in (bundle.mfr_url or "").lower()


def test_next_data_json_yields_finish_from_js_shell():
    from extract.page_state import extract_page_state

    html = """
    <html><body><div id="app"></div>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"product":{"sku":"42396",
      "specs":[{"name":"Finish","value":"Black"},{"name":"Blade Span","value":"52"}]}}}}
    </script></body></html>
    """
    bundle = extract_page_state(html, "https://www.kichler.com/products/42396")
    assert bundle.get("Finish").value == "Black"
    assert bundle.get("Blade Span").value == "52"


def test_desc_fields_are_cited_to_mfr_url_when_page_repeats_them():
    from extract.confirm import confirm_desc_evidence
    from extract.evidence import Evidence

    bundle = EvidenceBundle()
    bundle.set(
        Evidence(
            field="Blade Span",
            value="44",
            uom="in",
            source_url="input:Part_Desc",
            extractor="generic_desc_parser",
            confidence=0.65,
        )
    )
    bundle.set(
        Evidence(
            field="Finish",
            value="White",
            source_url="input:Part_Desc",
            extractor="generic_desc_parser",
            confidence=0.65,
        )
    )
    html = "<html><body>Dempsey 44 inch blade span. Finish: White.</body></html>"
    confirm_desc_evidence(
        bundle,
        html,
        "https://www.hunterfan.com/products/dempsey",
        ["hunterfan.com"],
    )
    assert bundle.get("Blade Span").source_url.startswith("https://www.hunterfan.com/")
    assert bundle.get("Finish").source_url.startswith("https://www.hunterfan.com/")


def test_short_number_is_not_rehomed_from_unrelated_page_text():
    from extract.confirm import confirm_desc_evidence
    from extract.evidence import Evidence

    bundle = EvidenceBundle()
    bundle.set(
        Evidence(
            field="Blade Span",
            value="44",
            uom="in",
            source_url="input:Part_Desc",
            extractor="generic_desc_parser",
            confidence=0.65,
        )
    )
    html = "<html><body>44 products in this collection. Free shipping.</body></html>"
    confirm_desc_evidence(
        bundle,
        html,
        "https://www.hunterfan.com/products/other",
        ["hunterfan.com"],
    )
    assert bundle.get("Blade Span").source_url == "input:Part_Desc"


def test_html_entities_confirm_desc_diameter():
    from extract.confirm import confirm_desc_evidence
    from extract.evidence import Evidence

    bundle = EvidenceBundle()
    bundle.set(
        Evidence(
            field="Diameter",
            value='5"',
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.7,
        )
    )
    html = "<html><body>Hiolit JCA2A0 5&quot; PSA Tab. Diameter : 5&quot;</body></html>"
    confirm_desc_evidence(
        bundle,
        html,
        "https://www.mirka.com/en-us/p/5B-332-080",
        ["mirka.com"],
    )
    assert bundle.get("Diameter").source_url.startswith("https://www.mirka.com/")


def test_live_fetch_rehomes_part_desc_citations(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    from extract.evidence import Evidence
    from sources.known_urls import remember_urls
    from sources.live_enrich import fetch_manufacturer_evidence

    product = "https://www.frigidaire.com/en/p/owner-center/product-support/X1"
    remember_urls("X1", [product])
    html = '<html><body>Diameter : 5&quot; Arbor Size : 7/8 in Thickness : .045 in</body></html>'
    _stub_fetch_pages(monkeypatch, lambda url: html if "frigidaire" in url else "")
    prior = EvidenceBundle()
    prior.set(
        Evidence(
            field="Diameter",
            value='5"',
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.7,
        )
    )
    fetch_manufacturer_evidence("X1", ["frigidaire.com"], fetch_pdfs=False, prior=prior)
    assert prior.get("Diameter").source_url == product


def test_empty_on_site_search_is_not_ingested(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    from sources.live_enrich import fetch_manufacturer_evidence

    empty = '<html><body><h4>0 results for "X1"</h4> Electric Sanders Gas Dual Fuel</body></html>'
    dist_html = (
        "<html><body>Voltage Rating 120 Color Stainless Steel "
        "Material Stainless Steel Buy it today</body></html>"
    )

    def html_for(url: str) -> str:
        if "search" in url.lower():
            return empty
        if "grainger.com" in url:
            return dist_html
        return ""

    _stub_fetch_pages(monkeypatch, html_for)
    bundle = fetch_manufacturer_evidence("X1", ["frigidaire.com"], fetch_pdfs=False)
    assert all("search" not in (item.source_url or "").lower() for item in bundle.items)
    assert "search" not in (bundle.mfr_url or "").lower()


def test_host_product_template_is_used_for_unseen_sku_not_only_the_demo_part():
    from sources.finder import candidate_mfr_urls, first_fetch_window

    urls = first_fetch_window(candidate_mfr_urls("ZZ-JUDGE-MKE", ["milwaukeetool.com"]), 6)
    joined = " ".join(urls)
    assert "https://www.milwaukeetool.com/products/details/ZZ-JUDGE-MKE" in urls
    assert "/Search/ZZ-JUDGE-MKE" not in joined
    assert "49-94-0013" not in joined


def test_host_product_template_beats_learned_appliance_404s():
    from sources.finder import candidate_mfr_urls, first_fetch_window

    urls = first_fetch_window(candidate_mfr_urls("ZZ-JUDGE-ABR", ["mirka.com"]), 6)
    joined = " ".join(urls)
    assert "https://www.mirka.com/en-us/p/ZZ-JUDGE-ABR" in urls
    assert "/appliance/" not in joined
    assert "/en-us/product/" not in joined
    assert "5B-332-080" not in joined


def test_search_only_host_still_guesses_generic_product_paths():
    from sources.finder import candidate_mfr_urls, first_fetch_window

    urls = first_fetch_window(candidate_mfr_urls("ZZ-JUDGE-3M", ["3m.com"]), 6)
    joined = " ".join(urls)
    assert any("/p/ZZ-JUDGE-3M" in url or "/products/ZZ-JUDGE-3M" in url for url in urls)
    assert "search" in joined.lower()


def test_web_search_finds_manufacturer_pdp_before_family_or_distributors(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "1")
    pdp = "https://www.frigidaire.com/catalog/item/ZZ-JUDGE-NEW"
    rich = (
        "<html><body>Voltage Rating 120 Color White "
        "Material Steel Amperage Rating 15</body></html>"
    )

    def html_for(url: str) -> str:
        return rich if "catalog/item" in url else ""

    requested = _stub_fetch_pages(monkeypatch, html_for)
    monkeypatch.setattr(
        "sources.live_enrich._discover_search_urls",
        lambda *args, **kwargs: ([pdp], ["frigidaire.com"], [pdp]),
    )
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("ZZ-JUDGE-NEW", ["frigidaire.com"], fetch_pdfs=False)
    joined = " ".join(requested).lower()
    assert pdp in requested
    assert bundle.get("Voltage Rating") is not None
    assert "catalog/item" in (bundle.mfr_url or "")
    assert "grainger.com" not in joined
    assert "electrolux.com" not in joined


def test_embedded_pdp_path_is_followed_from_js():
    from extract.ref_discovery import discover_product_links

    html = r"""
    <html><body><script>self.__next_f.push([1,"/products/details/5-x-045-x-7-8-metal-cut-off-wheel-type-1/49-94-0013"])</script></body></html>
    """
    links = discover_product_links(
        html,
        "https://www.milwaukeetool.com/search?q=49-94-0013",
        "49-94-0013",
        ["milwaukeetool.com"],
    )
    assert any("49-94-0013" in url and "/products/details/" in url for url in links)


def test_empty_oem_search_still_uses_allowed_fallbacks(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    empty = '<html><body><h4>0 results for "X1"</h4></body></html>'
    fallback = (
        "<html><body>Voltage Rating 120 Color White "
        "Material Steel Amperage Rating 15 Buy it today</body></html>"
    )

    def html_for(url: str) -> str:
        if "3m.com" in url:
            return empty
        if "energystar.gov" in url or "grainger.com" in url:
            return fallback
        return ""

    requested = _stub_fetch_pages(monkeypatch, html_for)
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("X1", ["3m.com"], fetch_pdfs=False)
    joined = " ".join(requested).lower()
    assert "energystar.gov" in joined
    voltage = bundle.get("Voltage Rating")
    assert voltage is not None
    assert voltage.confidence <= 0.68
    assert "3m.com" not in (voltage.source_url or "").lower()


def test_js_shell_manufacturer_page_still_uses_distributor_specs(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    scripts = "".join(f"<script>window._x{i}={{}}</script>" for i in range(10))
    shell = "<html><body><div id='app'></div>" + scripts + "<!-- " + ("z" * 12000) + " --></body></html>"
    dist_html = (
        "<html><body>Voltage Rating 120 Color White "
        "Material Steel Amperage Rating 15 Buy it today</body></html>"
    )

    def html_for(url: str) -> str:
        if "frigidaire." in url:
            return shell
        if "grainger.com" in url:
            return dist_html
        return ""

    requested = _stub_fetch_pages(monkeypatch, html_for)
    from sources.live_enrich import fetch_manufacturer_evidence

    bundle = fetch_manufacturer_evidence("X1", ["frigidaire.com"], fetch_pdfs=False)
    joined = " ".join(requested).lower()
    assert "grainger.com" in joined
    assert bundle.get("Voltage Rating") is not None
    assert "grainger.com" in (bundle.get("Voltage Rating").source_url or "")
    assert bundle.get("Voltage Rating").confidence <= 0.68
    assert "frigidaire.com" in (bundle.mfr_url or "")
    assert "grainger" not in (bundle.mfr_url or "").lower()


def test_settled_pdp_cancels_in_flight_urls(monkeypatch):
    import asyncio
    import time

    from sources.async_fetcher import fetch_all_pages

    async def fake_html(url, timeout=None, client=None):
        if "slow" in url:
            try:
                await asyncio.sleep(8)
            except asyncio.CancelledError:
                raise
            return 200, "<html>slow</html>", url
        html = (
            "<html><body>Voltage Rating 120 Color White "
            "Material Steel Amperage Rating 15</body></html>"
        )
        return 200, html, url

    monkeypatch.setattr("sources.async_fetcher.fetch_html_async", fake_html)
    monkeypatch.setattr("sources.async_fetcher._playwright_allowed", lambda url: False)

    seen = {"n": 0}

    def on_page(status, html, final_url, requested):
        seen["n"] += 1
        return "pdp" in requested

    started_at = time.monotonic()
    pages = asyncio.run(
        fetch_all_pages(
            [
                "https://www.frigidaire.com/p/pdp",
                "https://www.frigidaire.com/slow",
            ],
            timeout=15,
            on_page=on_page,
        )
    )
    elapsed = time.monotonic() - started_at
    assert elapsed < 3
    assert any("pdp" in item[3] for item in pages)
    assert seen["n"] >= 1


def test_vercel_skips_ipv6_retry_on_timeouts(monkeypatch):
    import asyncio

    monkeypatch.setenv("VERCEL", "1")
    stacks: list[bool] = []

    async def fake_html(url, timeout=None, client=None):
        return 0, "", url

    from sources import async_fetcher

    orig_client = async_fetcher._http_client

    def tracking_client(timeout: int, ipv4: bool):
        stacks.append(ipv4)
        return orig_client(timeout, ipv4)

    monkeypatch.setattr(async_fetcher, "fetch_html_async", fake_html)
    monkeypatch.setattr(async_fetcher, "_http_client", tracking_client)
    monkeypatch.setattr(async_fetcher, "_playwright_allowed", lambda url: False)

    asyncio.run(async_fetcher.fetch_all_pages(["https://www.frigidaire.com/p/X1"], timeout=2))
    assert stacks == [True]


def test_tool_brand_does_not_treat_appliance_path_as_product_cms():
    from app.config import FETCH_URL_LIMIT
    from sources.finder import candidate_mfr_urls, first_fetch_window

    urls = first_fetch_window(candidate_mfr_urls("JET-X", ["jettools.com"]), FETCH_URL_LIMIT)
    joined = " ".join(urls)
    assert "/appliance/" not in joined
    assert any("/product/" in url or "/p/" in url for url in urls)
    assert "https://www.jettools.com/search?q=JET-X" in urls


def test_ge_family_still_uses_appliance_product_path():
    from app.config import FETCH_URL_LIMIT
    from sources.finder import candidate_mfr_urls, first_fetch_window

    urls = first_fetch_window(candidate_mfr_urls("PDT715SYVFS", ["geappliances.com"]), FETCH_URL_LIMIT)
    assert any("/appliance/PDT715SYVFS" in url for url in urls)


def test_known_pdfs_are_extracted_not_html_fetched(tmp_path, monkeypatch):
    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
    pdp = "https://www.milwaukeetool.com/products/details/49-94-NEW"
    pdf = "https://www.milwaukeetool.com/-/media/PDFs/Objective-Data/guide.pdf"
    from sources.known_urls import remember_urls

    remember_urls("49-94-NEW", [pdp, pdf])
    pdf_seen: list[str] = []

    def capture_pdfs(urls):
        pdf_seen.extend(urls)
        return EvidenceBundle()

    rich = (
        "<html><body>Voltage Rating 120 Color White "
        "Material Steel Amperage Rating 15</body></html>"
    )
    requested = _stub_fetch_pages(monkeypatch, lambda url: rich if "products/details" in url else "")
    monkeypatch.setattr("sources.live_enrich.fetch_pdf_evidence", capture_pdfs)
    from sources.live_enrich import fetch_manufacturer_evidence

    fetch_manufacturer_evidence("49-94-NEW", ["milwaukeetool.com"], fetch_pdfs=True)
    assert all(not url.lower().endswith(".pdf") for url in requested)
    assert pdf in pdf_seen
    assert pdp in requested

