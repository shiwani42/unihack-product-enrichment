from sources.brand_harvest import host_has_product_template, map_proposal, sample_brand_rows
from sources.finder import candidate_mfr_urls, first_fetch_window
from sources.learned_paths import merge_learned_paths, mine_cross_host_paths, template_path_shape
from sources.url_patterns import portable_templates


def test_appliance_shape_is_learned_from_two_hosts():
    templates = {
        "cafeappliances.com": ["https://www.cafeappliances.com/appliance/{mpn}"],
        "geappliances.com": ["https://www.geappliances.com/appliance/{mpn}"],
        "frigidaire.com": ["https://www.frigidaire.com/en/p/owner-center/product-support/{mpn}"],
    }
    assert "/appliance/{mpn}" in mine_cross_host_paths(templates)
    assert all("owner-center" not in path for path in mine_cross_host_paths(templates))


def test_seed_cms_shape_fills_cap_for_unseen_hosts():
    templates = {
        "cafeappliances.com": ["https://www.cafeappliances.com/appliance/{mpn}"],
        "geappliances.com": ["https://www.geappliances.com/appliance/{mpn}"],
        "dewalt.com": ["https://www.dewalt.com/en-us/product/{mpn}"],
    }
    merged = merge_learned_paths(templates)
    assert merged[0] == "/appliance/{mpn}"
    assert "/en-us/product/{mpn}" in merged
    assert "owner-center" not in " ".join(merged)


def test_deep_brand_cms_is_not_a_generic_shape():
    assert template_path_shape(
        "https://www.frigidaire.com/en/p/owner-center/product-support/{mpn}"
    ) is None
    assert template_path_shape("https://www.southwire.com/search?q={mpn}") is None


def test_unseen_host_gets_learned_appliance_and_adobe_paths():
    from app.config import FETCH_URL_LIMIT

    urls = first_fetch_window(candidate_mfr_urls("ZZ-JUDGE-NEW", ["newbrandtools.com"]), FETCH_URL_LIMIT)
    joined = " ".join(urls)
    assert "https://www.newbrandtools.com/search?q=ZZ-JUDGE-NEW" in urls
    assert "https://www.newbrandtools.com/p/ZZ-JUDGE-NEW" in urls
    assert "https://www.newbrandtools.com/appliance/ZZ-JUDGE-NEW" in urls
    assert "https://www.newbrandtools.com/en-us/product/ZZ-JUDGE-NEW" in urls
    assert "owner-center" not in joined
    assert "gea-specs" not in joined


def test_satco_specsheet_is_portable():
    url = "https://www.satco.com/catalog/product/specsheets/65-1222"
    assert portable_templates(url, "65-1222") == [
        "https://www.satco.com/catalog/product/specsheets/{mpn}"
    ]


def test_host_product_template_detects_southwire():
    extras = {"southwire.com": ["https://www.southwire.com/p/{mpn}"]}
    assert host_has_product_template(["southwire.com"], extras)
    extras = {"kichler.com": ["https://www.kichler.com/search?q={mpn}"]}
    assert not host_has_product_template(["kichler.com"], extras)


def test_sample_leftover_includes_search_only_mapped_brands():
    from app.config import DEFAULT_INPUT
    from ingest.csv_io import read_input_rows

    leftover = sample_brand_rows(read_input_rows(DEFAULT_INPUT), scope="leftover")
    unmapped = sample_brand_rows(read_input_rows(DEFAULT_INPUT), scope="unmapped")
    mapped = sample_brand_rows(read_input_rows(DEFAULT_INPUT), scope="mapped")
    assert leftover
    assert len(unmapped) <= len(leftover)
    assert all(not row["_mapped"] for row in unmapped)
    assert all(row["_mapped"] for row in mapped)
    assert all(row["_leftover"] for row in leftover)
    assert all((row["_ident"].brand_key or row["_ident"].manufacturer_name) for row in leftover)


def test_map_proposal_needs_named_host_and_rich_pdp():
    base = {
        "mapped": False,
        "search_page": False,
        "brand_key": "Newbrand",
        "brand_name": "Newbrand",
        "manufacturer_name": "Newbrand Tools",
        "items": 4,
        "mfr_url": "https://www.newbrandtools.com/products/ZZ-1",
        "host": "newbrandtools.com",
        "fetch_mpn": "ZZ-1",
        "mpn": "ZZ-1",
    }
    assert map_proposal(base)["domains"] == ["newbrandtools.com"]
    search = {**base, "search_page": True, "mfr_url": "https://www.newbrandtools.com/search?q=ZZ-1"}
    assert map_proposal(search) is None
    grainger = {
        **base,
        "mfr_url": "https://www.grainger.com/product/ZZ-1",
        "host": "grainger.com",
    }
    assert map_proposal(grainger) is None


def test_generic_guess_url_detects_official_path_only():
    from sources.brand_harvest import _generic_guess_url

    assert _generic_guess_url("https://www.vv.com/p/D519127", "D519127")
    assert _generic_guess_url("https://www.rees.com/appliance/25-A", "25-A")
    assert not _generic_guess_url(
        "https://www.southwire.com/wire-cable/building-wire/p/13093005", "13093005"
    )


def test_drop_thin_promotions_removes_host_taught_by_empty_page():
    from sources.brand_harvest import _search_paths, _write_search_paths, drop_thin_promotions

    before = _search_paths()
    payload = dict(before)
    payload["vv.com"] = ["https://www.vv.com/p/{mpn}"]
    _write_search_paths(payload)
    dropped = drop_thin_promotions(before, [{"host": "vv.com", "items": 0, "mfr_url": "https://www.vv.com/p/X"}])
    assert "vv.com" in dropped
    assert "vv.com" not in _search_paths()
