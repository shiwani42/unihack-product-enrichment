"""Per-SKU product URLs remembered from live search."""

import json
from pathlib import Path

from extract.evidence import Evidence, EvidenceBundle
from sources.finder import best_mfr_url, candidate_mfr_urls
from sources.known_urls import (
    harvest_evidence_dir,
    known_urls_for,
    remember_bundle,
    remember_urls,
    url_worth_keeping,
)


def test_drops_junk_and_shopping_urls():
    assert not url_worth_keeping("https://leviton.com/error-pages/404")
    assert not url_worth_keeping("https://www.amazon.com/dp/X1")
    assert not url_worth_keeping("input:Part_Desc")
    assert not url_worth_keeping("https://www.southwire.com/p/x.jpg")
    assert url_worth_keeping("https://www.southwire.com/wire-cable/p/13093005")


def test_remember_roundtrip_prefers_product_page(tmp_path, monkeypatch):
    remember_urls(
        "13093005",
        [
            "https://www.southwire.com/search?q=13093005",
            "https://www.southwire.com/wire-cable/building-wire/seu-aluminum-service-entrance/p/13093005",
            "https://www.amazon.com/dp/13093005",
            "https://leviton.com/error-pages/404",
        ],
    )
    urls = known_urls_for("13093005")
    assert urls[0].endswith("/p/13093005")
    assert all("amazon." not in url for url in urls)
    assert all("error-pages" not in url for url in urls)
    assert all("search?" not in url for url in urls)


def test_known_url_is_tried_before_search_template():
    remember_urls("49-94-3000", ["https://www.milwaukeetool.com/en-us/49-94-3000"])
    urls = candidate_mfr_urls("49-94-3000", ["milwaukeetool.com"])
    assert urls[0] == "https://www.milwaukeetool.com/en-us/49-94-3000"
    assert best_mfr_url("49-94-3000", ["milwaukeetool.com"]) == urls[0]


def test_remember_bundle_saves_mfr_and_ref():
    bundle = EvidenceBundle(
        mfr_url="https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF",
        ref_urls=["https://support.frigidaire.com/Owner-Center/Product-Support/PDSH4816AF"],
    )
    bundle.set(
        Evidence(
            field="Series",
            value="Professional Series",
            source_url="https://support.frigidaire.com/Owner-Center/Product-Support/PDSH4816AF",
            extractor="html",
            confidence=0.9,
        )
    )
    remember_bundle("PDSH4816AF", bundle)
    urls = known_urls_for("PDSH4816AF")
    assert any("frigidaire.com" in url and "PDSH4816AF" in url for url in urls)


def test_harvest_keeps_gold_samples_and_real_product_pages():
    harvested = harvest_evidence_dir(Path(__file__).resolve().parents[1] / "data" / "evidence_cache")
    assert "https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF" in harvested["PDSH4816AF"]
    assert any("learnwhirlpool.com" in url for url in harvested["WDTS7024RZ"])
    assert any("/p/13093005" in url for url in harvested["13093005"])
    assert "R00-GFNT1-00K" not in harvested  # Leviton 404-only cache


def test_seed_file_includes_reference_sample_urls():
    path = Path(__file__).resolve().parents[1] / "sources" / "known_urls.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["PDSH4816AF"]
    assert data["WDTS7024RZ"]
    assert any("frigidaire.com" in url for url in data["PDSH4816AF"])
    assert any("learnwhirlpool.com" in url for url in data["WDTS7024RZ"])


def test_portable_template_applies_to_unseen_sku_on_same_host():
    from sources.finder import candidate_mfr_urls, reset_search_path_cache
    from sources.url_patterns import is_portable_template, portable_templates, promote_templates

    slug = "https://www.southwire.com/wire-cable/building-wire/seu-aluminum-service-entrance/p/13093005"
    assert portable_templates(slug, "13093005") == ["https://www.southwire.com/p/{mpn}"]
    assert not is_portable_template(
        "https://www.southwire.com/wire-cable/building-wire/seu-aluminum-service-entrance/p/{mpn}"
    )

    stable = "https://www.milwaukeetool.com/en-us/49-94-3000"
    assert portable_templates(stable, "49-94-3000") == ["https://www.milwaukeetool.com/en-us/{mpn}"]
    promote_templates("49-94-3000", [stable])
    reset_search_path_cache()
    unseen = candidate_mfr_urls("ZZ-NEW-SKU", ["milwaukeetool.com"])
    assert "https://www.milwaukeetool.com/en-us/ZZ-NEW-SKU" in unseen
    assert "https://www.milwaukeetool.com/en-us/49-94-3000" not in unseen


def test_frigidaire_owner_center_is_portable_across_mpns():
    from sources.url_patterns import portable_templates

    url = "https://www.frigidaire.com/en/p/owner-center/product-support/PDSH4816AF"
    assert portable_templates(url, "PDSH4816AF") == [
        "https://www.frigidaire.com/en/p/owner-center/product-support/{mpn}"
    ]


def test_unseen_sku_on_known_brand_uses_learned_host_template():
    from sources.finder import candidate_mfr_urls
    from sources.known_urls import known_urls_for

    assert known_urls_for("ZZ-JUDGE-FRIG") == []
    frig = candidate_mfr_urls("ZZ-JUDGE-FRIG", ["frigidaire.com"])
    assert "https://www.frigidaire.com/en/p/owner-center/product-support/ZZ-JUDGE-FRIG" in frig

    mke = candidate_mfr_urls("ZZ-JUDGE-MKE", ["milwaukeetool.com"])
    assert "https://www.milwaukeetool.com/products/details/ZZ-JUDGE-MKE" in mke
    assert "m18-brushless" not in " ".join(mke)
    from app.config import FETCH_URL_LIMIT
    from sources.finder import first_fetch_window

    window = first_fetch_window(mke, FETCH_URL_LIMIT)
    assert any("/products/details/ZZ-JUDGE-MKE" in url for url in window)
    assert any("search?q=ZZ-JUDGE-MKE" in url for url in window)

    sw = candidate_mfr_urls("ZZ-JUDGE-SW", ["southwire.com"])
    assert "https://www.southwire.com/p/ZZ-JUDGE-SW" in sw
    assert "seu-aluminum" not in " ".join(sw)


def test_slug_pdp_teaches_host_skeleton_for_the_next_part():
    from sources.finder import candidate_mfr_urls, reset_search_path_cache
    from sources.url_patterns import portable_templates

    milwaukee = "https://www.milwaukeetool.com/products/details/m18-brushless-precision-blower/0887-20"
    assert portable_templates(milwaukee, "0887-20") == [
        "https://www.milwaukeetool.com/products/details/{mpn}"
    ]
    remember_urls("0887-20", [milwaukee])
    reset_search_path_cache()
    unseen = candidate_mfr_urls("ZZ-MKE-NEW", ["milwaukeetool.com"])
    assert "https://www.milwaukeetool.com/products/details/ZZ-MKE-NEW" in unseen
    assert "m18-brushless-precision-blower" not in " ".join(unseen)


def test_glued_filename_is_not_a_host_template():
    from sources.url_patterns import portable_templates

    glued = "https://www.kitchenaid.com/owners-center-pdp.KSES530SBE0.html"
    assert portable_templates(glued, "KSES530SBE") == []
    assert portable_templates("https://avspare.com/0887-20", "0887-20") == []
    assert portable_templates("https://postal-codes.net/13093005", "13093005") == []


def test_error_url_is_not_kept():
    from sources.page_ok import is_error_url, is_not_found, is_usable_page

    assert is_error_url("https://leviton.com/error-pages/404")
    assert is_not_found(200, "<html><title>404 Page Not Found</title></html>", "https://www.leviton.com/p/X")
    assert not is_usable_page(200, "<html><title>404</title></html>", "https://leviton.com/error-pages/404")
    assert not is_usable_page(404, "<html>missing</html>", "https://www.leviton.com/p/X")
    assert is_usable_page(200, "<html><title>15A Outlet</title><body>spec</body></html>", "https://www.leviton.com/products/X")


def test_one_404_does_not_disable_path_for_other_skus():
    from sources.dead_paths import note_outcome
    from sources.finder import candidate_mfr_urls

    note_outcome(
        "https://www.leviton.com/products/A1",
        "A1",
        404,
        "",
        "https://leviton.com/error-pages/404",
    )
    urls = candidate_mfr_urls("C3", ["leviton.com"])
    assert "https://www.leviton.com/products/C3" in urls


def test_repeated_404s_skip_that_host_path():
    from sources.dead_paths import note_outcome
    from sources.finder import candidate_mfr_urls

    for mpn in ("A1", "B2"):
        note_outcome(
            f"https://www.leviton.com/products/{mpn}",
            mpn,
            404,
            "",
            "https://leviton.com/error-pages/404",
        )
    urls = candidate_mfr_urls("C3", ["leviton.com"])
    assert "https://www.leviton.com/products/C3" not in urls
    assert "https://www.leviton.com/search?q=C3" in urls
