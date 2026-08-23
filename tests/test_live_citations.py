"""Live manufacturer specs must beat Part_Desc for any SKU, not a brand allowlist."""

from extract.confirm import confirm_desc_evidence
from extract.evidence import Evidence, EvidenceBundle
from extract.html_specs import extract_from_html
from extract.merge import merge_bundles
from extract.page_state import extract_page_state
from extract.structured import extract_structured_data
from normalize.aliases import align_bundle_to_template
from pipeline import _fetch_evidence


def test_equal_confidence_live_spec_replaces_part_desc():
    desc = EvidenceBundle()
    desc.set(
        Evidence(
            field="Diameter",
            value='5"',
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.7,
        )
    )
    live = EvidenceBundle()
    live.set(
        Evidence(
            field="Diameter",
            value="6",
            uom="in",
            source_url="https://tools.example.com/p/UNSEEN1",
            extractor="html_regex",
            confidence=0.7,
        )
    )
    merged = merge_bundles(desc, live)
    item = merged.get("Diameter")
    assert item.value == "6"
    assert item.source_url.startswith("https://tools.example.com/")


def test_equivalent_live_value_rehomes_part_desc_citation():
    bundle = EvidenceBundle()
    bundle.set(
        Evidence(
            field="Diameter",
            value='5"',
            uom="in",
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.7,
        )
    )
    bundle.set(
        Evidence(
            field="Diameter",
            value="5 in",
            uom="in",
            source_url="https://abrasives.example.com/p/UNSEEN2",
            extractor="labeled_html",
            confidence=0.7,
        )
    )
    item = bundle.get("Diameter")
    assert item.value == '5"'
    assert item.source_url.startswith("https://abrasives.example.com/")


def test_weaker_live_extract_does_not_clobber_part_desc():
    bundle = EvidenceBundle()
    bundle.set(
        Evidence(
            field="Finish",
            value="White",
            source_url="input:Part_Desc",
            extractor="generic_desc_parser",
            confidence=0.7,
        )
    )
    bundle.set(
        Evidence(
            field="Finish",
            value="Almond",
            source_url="https://mfr.example.com/p/X",
            extractor="html_regex",
            confidence=0.5,
        )
    )
    assert bundle.get("Finish").value == "White"
    assert bundle.get("Finish").source_url == "input:Part_Desc"


def test_unknown_json_ld_property_becomes_evidence():
    html = """
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","sku":"UNSEEN3",
     "additionalProperty":[
       {"@type":"PropertyValue","name":"Wheel Type","value":"Type 1"},
       {"@type":"PropertyValue","name":"Maximum Speed","value":"13300 RPM"}
     ]}
    </script></head><body></body></html>
    """
    bundle = extract_structured_data(html, "https://oem.example.com/p/UNSEEN3")
    assert bundle.get("Wheel Type").value == "Type 1"
    assert bundle.get("Maximum Speed").value == "13300 RPM"
    assert bundle.get("Wheel Type").source_url.startswith("https://oem.example.com/")


def test_next_data_unknown_spec_name_is_kept():
    html = """
    <html><body><div id="app"></div>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"product":{"sku":"UNSEEN4",
      "specs":[{"name":"Hook and Loop","value":"Yes"},
               {"name":"Backing","value":"PSA"}]}}}}
    </script></body></html>
    """
    bundle = extract_page_state(html, "https://js-oem.example.com/p/UNSEEN4")
    assert bundle.get("Hook and Loop").value == "Yes"
    assert bundle.get("Backing").value == "PSA"


def test_html_table_and_definition_list_yield_specs():
    html = """
    <html><body>
      <dl>
        <dt>Arbor Size</dt><dd>7/8 in</dd>
        <dt>Grit Size</dt><dd>P80</dd>
      </dl>
      <table>
        <tr><th>Wheel Type</th><td>Type 1</td></tr>
        <tr><th>Maximum RPM</th><td>13300</td></tr>
      </table>
    </body></html>
    """
    bundle = extract_from_html(html, "https://catalog.example.com/p/UNSEEN5")
    arbor = bundle.get("Arbor Size")
    assert arbor is not None
    assert arbor.value.replace(" ", "").startswith("7/8")
    assert bundle.get("Grit Size").value == "P80"
    assert bundle.get("Wheel Type").value == "Type 1"
    assert "13300" in (bundle.get("Maximum RPM").value or "")
    assert arbor.source_url.startswith("https://catalog.example.com/")


def test_confirm_matches_inch_wording():
    bundle = EvidenceBundle()
    bundle.set(
        Evidence(
            field="Diameter",
            value='5"',
            uom="in",
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.7,
        )
    )
    html = "<html><body>Product specs. Diameter: 5 in. Type 1 wheel.</body></html>"
    confirm_desc_evidence(
        bundle,
        html,
        "https://www.unseen-tools.example.com/products/UNSEEN6",
        ["unseen-tools.example.com"],
    )
    assert bundle.get("Diameter").source_url.startswith("https://www.unseen-tools.example.com/")


def test_align_promotes_live_alias_over_part_desc_label():
    from classify.category_router import load_template

    template = load_template("metal_cutoff_disc")
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
    bundle.set(
        Evidence(
            field="Wheel Diameter",
            value="5 in",
            source_url="https://oem.example.com/p/UNSEEN7",
            extractor="extruct",
            confidence=0.78,
        )
    )
    aligned = align_bundle_to_template(bundle, template)
    item = aligned.get("Diameter")
    assert item.source_url.startswith("https://oem.example.com/")


def test_equal_confidence_alias_replaces_part_desc_value():
    from classify.category_router import load_template

    template = load_template("metal_cutoff_disc")
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
    bundle.set(
        Evidence(
            field="Wheel Diameter",
            value="6",
            uom="in",
            source_url="https://oem.example.com/p/UNSEEN9",
            extractor="labeled_html",
            confidence=0.7,
        )
    )
    aligned = align_bundle_to_template(bundle, template)
    item = aligned.get("Diameter")
    assert item.value == "6"
    assert item.source_url.startswith("https://oem.example.com/")


def test_suffix_label_from_any_brand_beats_part_desc():
    from classify.category_router import load_template
    from normalize.mapper import apply_template_attributes

    template = load_template("metal_cutoff_disc")
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
    bundle.set(
        Evidence(
            field="Outside Diameter",
            value="4.5",
            uom="in",
            source_url="https://unseen-tools.example.com/p/ZZ-JUDGE",
            extractor="labeled_html",
            confidence=0.8,
        )
    )
    aligned = align_bundle_to_template(bundle, template)
    assert aligned.get("Diameter").value == "4.5"
    assert aligned.get("Diameter").source_url.startswith("https://unseen-tools.example.com/")
    row: dict[str, str] = {}
    apply_template_attributes(row, template, aligned)
    assert row["ATTRIBUTE_VALUE 1"] == "4.5"


def test_confirm_rehomes_without_mapped_manufacturer_domain():
    bundle = EvidenceBundle()
    bundle.set(
        Evidence(
            field="Diameter",
            value='5"',
            uom="in",
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.7,
        )
    )
    html = "<html><body>Product specs. Diameter: 5 in. Type 1 wheel.</body></html>"
    confirm_desc_evidence(
        bundle,
        html,
        "https://www.unseen-oem.example.com/products/ZZ-1",
        [],
    )
    assert bundle.get("Diameter").source_url.startswith("https://www.unseen-oem.example.com/")


def test_attribute_citation_follows_live_alias_not_part_desc():
    from classify.category_router import load_template
    from normalize.mapper import apply_template_attributes
    from pipeline import _field_sources_from_bundle

    template = load_template("metal_cutoff_disc")
    bundle = EvidenceBundle()
    bundle.mfr_url = "https://oem.example.com/p/UNSEEN10"
    bundle.set(
        Evidence(
            field="Diameter",
            value='5"',
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.7,
        )
    )
    bundle.set(
        Evidence(
            field="Wheel Diameter",
            value="6",
            uom="in",
            source_url="https://oem.example.com/p/UNSEEN10",
            extractor="labeled_html",
            confidence=0.7,
        )
    )
    aligned = align_bundle_to_template(bundle, template)
    row: dict[str, str] = {}
    apply_template_attributes(row, template, aligned)
    sources = _field_sources_from_bundle(aligned, row)
    assert row["ATTRIBUTE_VALUE 1"] == "6"
    assert sources["ATTRIBUTE_VALUE 1"].startswith("https://oem.example.com/")
    assert not sources["ATTRIBUTE_VALUE 1"].startswith("input:")
    assert sources["Diameter"].startswith("https://oem.example.com/")


def test_preview_source_column_uses_manufacturer_url_not_part_desc():
    from app.ui_sections import row_preview

    preview = row_preview(
        {
            "Mfg_Part_Num": "49-94-0013",
            "MFR URL": "https://www.milwaukeetool.com/products/details/49-94-0013",
            "ATTRIBUTE_LABEL 1": "Diameter",
            "ATTRIBUTE_VALUE 1": "5",
            "ATTRIBUTE_UOM 1": "in",
            "ATTRIBUTE_LABEL 4": "Application",
            "ATTRIBUTE_VALUE 4": "Metal Cut Off Disc",
        },
        {
            "mpn": "49-94-0013",
            "field_sources": {
                "Diameter": "input:Part_Desc",
                "ATTRIBUTE_VALUE 1": "https://www.milwaukeetool.com/products/details/49-94-0013",
                "Application": "input:Part_Desc",
                "ATTRIBUTE_VALUE 4": "input:Part_Desc",
                "MFR URL": "https://www.milwaukeetool.com/products/details/49-94-0013",
            },
        },
    )
    sources = {spec["label"]: spec["source"] for spec in preview["specs"]}
    assert sources["Diameter"].startswith("https://www.milwaukeetool.com/")
    assert sources["Application"].startswith("https://www.milwaukeetool.com/")
    assert "input:Part_Desc" not in sources.values()


def test_preview_keeps_part_desc_when_mfr_url_is_only_a_search_page():
    from app.ui_sections import row_preview

    preview = row_preview(
        {
            "Mfg_Part_Num": "X1",
            "MFR URL": "https://www.brand.com/search?q=X1",
            "ATTRIBUTE_LABEL 1": "Color",
            "ATTRIBUTE_VALUE 1": "White",
        },
        {
            "field_sources": {
                "Color": "input:Part_Desc",
                "ATTRIBUTE_VALUE 1": "input:Part_Desc",
                "MFR URL": "https://www.brand.com/search?q=X1",
            },
        },
    )
    assert preview["specs"][0]["source"] == "input:Part_Desc"


def test_pipeline_merge_cites_manufacturer_not_part_desc(tmp_path, monkeypatch):
    import pipeline as pipeline_module
    from identity.brand_resolver import Identity

    monkeypatch.setattr("extract.cache.CACHE_DIR", tmp_path)
    monkeypatch.setenv("UNILOG_LIVE_FETCH", "1")

    desc = EvidenceBundle()
    desc.set(
        Evidence(
            field="Diameter",
            value='5"',
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.7,
        )
    )

    def fake_fetch(mpn, domains, max_urls=None, fetch_pdfs=True, **kwargs):
        live = EvidenceBundle(mfr_url=f"https://{domains[0]}/p/{mpn}")
        live.set(
            Evidence(
                field="Diameter",
                value="5",
                uom="in",
                source_url=f"https://{domains[0]}/p/{mpn}",
                extractor="labeled_html",
                confidence=0.7,
            )
        )
        return live

    monkeypatch.setattr(pipeline_module, "fetch_manufacturer_evidence", fake_fetch)
    identity = Identity(
        brand_key="Acme",
        brand_name="ACME",
        manufacturer_name="Acme Corp",
        method="test",
        confidence=0.8,
        domains=["oem.example.com"],
    )
    merged = _fetch_evidence("UNSEEN8", "UNSEEN8", identity, desc, "metal_cutoff_disc")
    assert merged.get("Diameter").source_url.startswith("https://oem.example.com/")
    assert not merged.get("Diameter").source_url.startswith("input:")
