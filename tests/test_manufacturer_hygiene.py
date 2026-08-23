"""Dealer hosts, Icecat search crumbs, and storefront CSS must not become manufacturer evidence."""

from extract.evidence import Evidence, EvidenceBundle
from extract.labeled_specs import extract_labeled_specs
from normalize.mapper import apply_template_attributes
from normalize.values import cleanse_attribute, cleanse_output_row
from sources.domain_discovery import discover_domains_from_urls, select_search_hits
from sources.finder import (
    host_uses_appliance_path,
    is_blocked_url,
    is_search_url,
    looks_like_dealer_storefront,
    official_url_score,
)
from sources.source_policy import classify_url


BAYSHORE = (
    "https://www.bayshoreappliance.com/appliances/kitchen-cleanup/"
    "dishwashers/built-in-dishwasher/frigidaire/PDSH4816AF"
)


def test_local_appliance_dealer_is_not_a_manufacturer_host():
    assert looks_like_dealer_storefront(BAYSHORE)
    assert is_blocked_url(BAYSHORE)
    assert classify_url(BAYSHORE, ["frigidaire.com"]) == "blocked"
    assert official_url_score(BAYSHORE, "PDSH4816AF") < 0
    assert not host_uses_appliance_path("bayshoreappliance.com")
    assert host_uses_appliance_path("geappliances.com")
    assert host_uses_appliance_path("products.geappliances.com")


def test_search_does_not_adopt_dealer_appliance_path_as_oem():
    urls = [
        BAYSHORE,
        "https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF",
        "https://www.riversace.com/appliances/kitchen-cleanup/dishwashers/built-in-dishwasher/ge-profile/PDD415PYYFS",
        "https://www.kellyshomecenter.com/appliances/kitchen-cleanup/dishwashers/built-in-dishwasher/kitchenaid/KDTS324SPS",
        "https://queencityonline.com/appliances/laundry/dryers/electric-match-front-load-dryers/speed-queen/DF7004WE",
        "https://karlsonline.com/appliances/laundry/top-load-matching/top-load-matching-electric-dryer/speed-queen/DR7004BE",
        "https://www.brothersmain.com/appliances/laundry/washers/traditional-top-load-washer/speed-queen/TR7006BN",
        "https://shopjetson.com/appliances/laundry/commercial-laundry/commercial-dryer/speed-queen/DV2000WE",
        "https://www.vanvreedes.com/appliances/cooking/ranges?pnf=1",
    ]
    domains = discover_domains_from_urls(urls, mpn="PDSH4816AF", names=["Frigidaire"])
    assert "bayshoreappliance.com" not in domains
    assert "riversace.com" not in domains
    assert "kellyshomecenter.com" not in domains
    assert "frigidaire.com" in domains
    for url in urls:
        if "frigidaire.com" in url:
            continue
        assert looks_like_dealer_storefront(url)
        assert is_blocked_url(url)
    hits, extra = select_search_hits(urls, ["frigidaire.com"], "PDSH4816AF", ["Frigidaire"], limit=10)
    assert all("bayshore" not in url for url in hits)
    assert all("/appliances/" not in url for url in hits)
    assert extra == [] or "bayshoreappliance.com" not in extra


def test_brand_matched_host_beats_unnamed_catalog_product_path():
    urls = [
        "https://www.newsourceindustrial.example/Product/ZZ-NEW-SKU",
        "https://www.acmetoolsbrand.com/search?q=ZZ-NEW-SKU",
        "https://www.acmetoolsbrand.com/p/ZZ-NEW-SKU",
    ]
    domains = discover_domains_from_urls(urls, mpn="ZZ-NEW-SKU", names=["Acme Tools Brand"])
    assert "acmetoolsbrand.com" in domains
    assert "newsourceindustrial.example" not in domains


def test_parent_company_product_url_still_discovered():
    domains = discover_domains_from_urls(
        ["https://www.abb.com/products/A410RCAR"],
        mpn="A410RCAR",
        names=["Carlon"],
    )
    assert "abb.com" in domains


def test_icecat_query_is_a_search_page_not_a_ref():
    assert is_search_url("https://icecat.us/?q=PDSH4816AF")
    assert is_search_url("https://icecat.biz/search?keyword=X1")
    assert is_blocked_url("https://icecat.us/?q=PDSH4816AF")
    from sources.finder import candidate_third_party_urls

    joined = " ".join(candidate_third_party_urls("X1")).lower()
    assert "icecat." not in joined
    assert "energystar.gov" in joined


def test_storefront_css_and_town_are_not_specs():
    html = """
    <html><body>
      <dl>
        <dt>Size</dt><dd>1440</dd>
        <dt>Color</dt><dd>#444</dd>
        <dt>town_name</dt><dd>Hazlet, NJ</dd>
        <dt>sep</dt><dd>|</dd>
        <dt>With</dt><dd>with more than</dd>
        <dt>Voltage Rating</dt><dd>5</dd>
      </dl>
    </body></html>
    """
    bundle = extract_labeled_specs(html, BAYSHORE)
    assert bundle.get("Size") is None or bundle.get("Size").value != "1440"
    assert bundle.get("Color") is None
    assert bundle.get("town_name") is None
    assert bundle.get("With") is None
    value, uom = cleanse_attribute("Voltage Rating", "5", "V", "built_in_dishwasher")
    assert value == ""
    value, uom = cleanse_attribute("Size", "4", "", "built_in_dishwasher")
    assert value == ""
    value, uom = cleanse_attribute("Size", "1440", "", "built_in_dishwasher")
    assert value == ""
    value, uom = cleanse_attribute("Color", "#444", "", "built_in_dishwasher")
    assert value == ""
    value, uom = cleanse_attribute("With", "with more than", "", "generic_industrial")
    assert value == ""
    value, uom = cleanse_attribute("Voltage Rating", "15", "V", "built_in_dishwasher")
    assert value == ""
    value, uom = cleanse_attribute("Voltage Rating", "120", "V", "built_in_dishwasher")
    assert value == "120"
    value, uom = cleanse_attribute("Wattage", "5", "W", "built_in_dishwasher")
    assert value == ""
    value, uom = cleanse_attribute("Wattage", "9", "W", "led_lighting")
    assert value == "9"


def test_opengraph_pixel_width_is_not_product_size():
    from extract.structured import extract_structured_data

    html = """
    <html><head>
      <meta property="og:image:width" content="1440">
      <script type="application/ld+json">
      {"@type":"LocalBusiness","name":"Bayshore","address":{"@type":"PostalAddress",
        "addressLocality":"Hazlet","addressRegion":"NJ"},
        "additionalProperty":[{"name":"width","value":"1440"},{"name":"color","value":"#444"},
        {"name":"town_name","value":"Hazlet, NJ"}]}
      </script>
    </head><body></body></html>
    """
    bundle = extract_structured_data(html, BAYSHORE)
    assert bundle.get("Size") is None or bundle.get("Size").value != "1440"
    assert bundle.get("Color") is None or not str(bundle.get("Color").value).startswith("#")
    assert bundle.get("town_name") is None


def test_distributor_catalog_is_not_adopted_as_manufacturer():
    from sources.finder import is_distributor_url

    url = "https://www.sourceatlantic.ca/Product/7100075678"
    assert is_distributor_url(url)
    domains = discover_domains_from_urls([url], mpn="7100075678", names=["3M"])
    assert "sourceatlantic.ca" not in domains
    assert classify_url(url, ["3m.com"]) == "distributor"


def test_angular_template_junk_is_dropped():
    value, _uom = cleanse_attribute(
        "Application",
        "{{attributeValue}}",
        "",
        "generic_industrial",
    )
    assert value == ""
    row = {"With": "with more than", "ATTRIBUTE_LABEL 1": "With", "ATTRIBUTE_VALUE 1": "with more than"}
    cleanse_output_row(row, "generic_industrial")
    assert row.get("With", "") == ""
    assert row.get("ATTRIBUTE_VALUE 1", "") == ""


def test_dealer_specs_do_not_fill_template_slots():
    from classify.category_router import load_template

    template = load_template("built_in_dishwasher")
    bundle = EvidenceBundle()
    bundle.set(Evidence(field="Size", value="1440", source_url=BAYSHORE, extractor="html", confidence=0.8))
    bundle.set(Evidence(field="Color", value="#444", source_url=BAYSHORE, extractor="html", confidence=0.8))
    bundle.set(Evidence(field="town_name", value="Hazlet, NJ", source_url=BAYSHORE, extractor="html", confidence=0.8))
    row: dict[str, str] = {"Mfg_Part_Num": "PDSH4816AF"}
    apply_template_attributes(row, template, bundle)
    cleanse_output_row(row, "built_in_dishwasher")
    labels = [row.get(f"ATTRIBUTE_LABEL {i}", "") for i in range(1, 51)]
    assert "town_name" not in labels
    for index, label in enumerate(labels, start=1):
        if label == "Size":
            assert row.get(f"ATTRIBUTE_VALUE {index}", "") != "1440"
        if label == "Color":
            assert row.get(f"ATTRIBUTE_VALUE {index}", "") != "#444"
