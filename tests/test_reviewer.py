"""Inspect-drawer reviewer hints: typed specs, flags, and remembered URLs."""

from classify.category_router import load_template
from extract.evidence import Evidence, EvidenceBundle
from ingest.csv_io import empty_output_row, load_output_headers
from normalize.mapper import apply_template_attributes
from sources.finder import is_blocked_url
from sources.known_urls import known_urls_for
from sources.learned_hosts import is_learned_storefront
from sources.reviewer import (
    contribute,
    hint_url_allowed,
    is_rejected_value,
    note_flag,
)


def test_shopping_hint_url_is_rejected():
    assert hint_url_allowed("https://www.amazon.com/dp/ZZ1") == ""
    assert hint_url_allowed("https://127.0.0.1/p/ZZ1") == ""
    assert hint_url_allowed("https://www.acmetoolsbrand.com/p/ZZ-NEW-SKU").endswith("/p/ZZ-NEW-SKU")


def test_typed_attribute_fills_and_is_reapplied():
    headers = load_output_headers()
    result = contribute(
        mpn="ZZ-REVIEW-1",
        preview={
            "mpn": "ZZ-REVIEW-1",
            "category_id": "generic_industrial",
            "input": {"Mfg_Part_Num": "ZZ-REVIEW-1", "Part_Desc": "Brass fitting"},
            "specs": [],
        },
        row=None,
        headers=headers,
        attributes=[{"label": "Material", "value": "Brass"}],
        category_id="generic_industrial",
    )
    row = result["row"]
    labels = [row.get(f"ATTRIBUTE_LABEL {i}") for i in range(1, 51)]
    values = [row.get(f"ATTRIBUTE_VALUE {i}") for i in range(1, 51)]
    assert "Material" in labels
    assert "Brass" in values

    later = empty_output_row(headers)
    later["Mfg_Part_Num"] = "ZZ-REVIEW-1"
    from sources.reviewer import apply_saved_overrides

    apply_saved_overrides(later, "ZZ-REVIEW-1")
    assert "Brass" in [later.get(f"ATTRIBUTE_VALUE {i}") for i in range(1, 51)]


def test_flagged_pixel_size_is_rejected_for_later_skus():
    note_flag("ZZ-REVIEW-2", "Size", "1440", "That's the OG image width")
    assert is_rejected_value("Size", "1440")
    headers = load_output_headers()
    row = empty_output_row(headers)
    template = load_template("generic_industrial")
    bundle = EvidenceBundle()
    bundle.set(Evidence(field="Size", value="1440", source_url="https://www.acmetoolsbrand.com/p/X", extractor="html", confidence=0.8))
    apply_template_attributes(row, template, bundle)
    assert "1440" not in [row.get(f"ATTRIBUTE_VALUE {i}") for i in range(1, 51)]


def test_dealer_flag_remembers_storefront_host():
    url = "https://www.newdealer.example/catalog/p/ZZ-REVIEW-3"
    note_flag("ZZ-REVIEW-3", "Color", "#444", "dealer storefront, not the manufacturer", url)
    assert is_learned_storefront(url)
    assert is_blocked_url(url)


def test_hint_url_is_remembered_even_when_page_is_thin(monkeypatch):
    monkeypatch.setattr("sources.reviewer.fetch_hint_html", lambda url: (200, "<html><body>ok</body></html>", url))
    headers = load_output_headers()
    url = "https://www.acmetoolsbrand.com/p/ZZ-REVIEW-4"
    result = contribute(
        mpn="ZZ-REVIEW-4",
        preview={"mpn": "ZZ-REVIEW-4", "category_id": "generic_industrial", "input": {"Mfg_Part_Num": "ZZ-REVIEW-4"}, "specs": []},
        row=None,
        headers=headers,
        url=url,
        names=["Acme Tools Brand"],
        category_id="generic_industrial",
    )
    assert any("acmetoolsbrand.com" in item for item in known_urls_for("ZZ-REVIEW-4"))
    assert result["row"].get("MFR URL") == url or any(
        (result["row"].get(f"Ref URL {i}") or "") == url for i in range(1, 6)
    )


def test_hint_fetch_fills_empty_specs(monkeypatch):
    html = """
    <html><body>
      <dl>
        <dt>Voltage Rating</dt><dd>120 V</dd>
        <dt>Color</dt><dd>White</dd>
      </dl>
    </body></html>
    """
    monkeypatch.setattr("sources.reviewer.fetch_hint_html", lambda url: (200, html, url))
    headers = load_output_headers()
    result = contribute(
        mpn="ZZ-REVIEW-5",
        preview={
            "mpn": "ZZ-REVIEW-5",
            "category_id": "generic_industrial",
            "input": {"Mfg_Part_Num": "ZZ-REVIEW-5", "Part_Desc": "Fitting"},
            "specs": [{"slot": 1, "label": "Product Type", "value": "Fitting", "uom": "", "display": "Fitting", "source": ""}],
        },
        row=None,
        headers=headers,
        url="https://www.acmetoolsbrand.com/p/ZZ-REVIEW-5",
        names=["Acme Tools Brand"],
        category_id="generic_industrial",
    )
    values = " ".join(result["row"].get(f"ATTRIBUTE_VALUE {i}") or "" for i in range(1, 51))
    assert "120" in values or "White" in values
    assert result["row"].get("ATTRIBUTE_VALUE 1") == "Fitting"
