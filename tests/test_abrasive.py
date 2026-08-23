from app.config import DEFAULT_INPUT
from classify.category_router import route_category
from identity.brand_resolver import resolve_identity
from ingest.csv_io import read_input_rows
from pipeline import enrich_input_row
from ingest.csv_io import load_output_headers


def test_abrasive_routing_and_enrichment():
    headers = load_output_headers()
    rows = read_input_rows(DEFAULT_INPUT)
    sample = next(row for row in rows if "Metal Cut Off Disc" in row["Part_Desc"])
    identity = resolve_identity(
        sample["Mfg_Part_Num"],
        sample["Part_Desc"],
        sample["E1_Brand"],
        sample["DIB_Brand"],
    )
    template = route_category(sample["Part_Desc"], identity.brand_key)
    assert template is not None
    assert template.category_id == "metal_cutoff_disc"
    result = enrich_input_row(sample, headers)
    assert result.row["Classpath"]
    assert result.row["ATTRIBUTE_LABEL 1"] == "Diameter"


def test_extra_specs_overflow_into_unused_attribute_slots():
    from classify.category_router import load_template
    from extract.evidence import Evidence, EvidenceBundle
    from normalize.mapper import apply_template_attributes

    template = load_template("metal_cutoff_disc")
    bundle = EvidenceBundle()
    bundle.set(
        Evidence(field="Diameter", value="5", uom="in", source_url="https://mfr.com/x", extractor="html", confidence=0.8)
    )
    bundle.set(
        Evidence(field="Wheel Type", value="Type 1", source_url="https://mfr.com/x", extractor="html", confidence=0.8)
    )
    bundle.set(
        Evidence(
            field="Application",
            value="Metal Cut Off Disc",
            source_url="input:Part_Desc",
            extractor="desc_regex",
            confidence=0.65,
        )
    )
    row: dict[str, str] = {}
    apply_template_attributes(row, template, bundle)
    assert row["ATTRIBUTE_LABEL 1"] == "Diameter"
    assert row["ATTRIBUTE_VALUE 1"] == "5"
    labels = [row.get(f"ATTRIBUTE_LABEL {i}", "") for i in range(1, 51)]
    assert "Wheel Type" in labels
    slot = labels.index("Wheel Type") + 1
    assert slot > len(template.attribute_labels)
    assert row[f"ATTRIBUTE_VALUE {slot}"] == "Type 1"
    assert row["Application"] == "Metal Cut Off Disc"


def test_second_pass_fills_named_columns_and_empty_template_slots():
    from classify.category_router import load_template
    from extract.evidence import Evidence, EvidenceBundle
    from ingest.crosswalk import apply_product_ids
    from normalize.mapper import apply_template_attributes

    template = load_template("metal_cutoff_disc")
    bundle = EvidenceBundle()
    bundle.set(Evidence(field="Wheel Diameter", value="6", uom="in", source_url="https://mfr.com/x", extractor="html", confidence=0.8))
    bundle.set(Evidence(field="Pack Quantity", value="50", source_url="https://mfr.com/x", extractor="html", confidence=0.8))
    bundle.set(Evidence(field="Weight", value="2.4", uom="lb", source_url="https://mfr.com/x", extractor="html", confidence=0.8))
    bundle.set(Evidence(field="Includes", value="Guard", source_url="https://mfr.com/x", extractor="html", confidence=0.75))
    bundle.set(Evidence(field="GTIN", value="00883491123456", source_url="https://mfr.com/x", extractor="html", confidence=0.82))
    bundle.set(Evidence(field="Country Of Origin", value="China", source_url="https://mfr.com/x", extractor="html", confidence=0.75))
    bundle.set(Evidence(field="Wheel Type", value="Type 1", source_url="https://mfr.com/x", extractor="html", confidence=0.8))
    row: dict[str, str] = {"Mfg_Part_Num": "ZZ-1"}
    apply_template_attributes(row, template, bundle)
    apply_product_ids(row, bundle)
    assert row["ATTRIBUTE_LABEL 1"] == "Diameter"
    assert row["ATTRIBUTE_VALUE 1"] == "6"
    assert row["ATTRIBUTE_VALUE 7"] == "50"
    assert row["Selling Qty"] == "50"
    assert row["WEIGHT"] == "2.4"
    assert row["WEIGHT_UOM"] == "lb"
    assert row["Includes"] == "Guard"
    assert row["Country Of Origin"] == "China"
    assert row["GTIN"] == "00883491123456"
    assert row["Standard Packaging Information"] == "Pack of 50"
    labels = [row.get(f"ATTRIBUTE_LABEL {i}", "") for i in range(1, 51)]
    assert "Wheel Type" in labels
    assert "Weight" not in labels
    assert "GTIN" not in labels


def test_json_ld_gtin_and_pack_quantity_become_evidence():
    from extract.structured import extract_structured_data

    html = """
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","sku":"UNSEEN-GTIN",
     "additionalProperty":[
       {"@type":"PropertyValue","name":"GTIN","value":"0123456789012"},
       {"@type":"PropertyValue","name":"Pack Quantity","value":"25"}
     ]}
    </script></head><body></body></html>
    """
    bundle = extract_structured_data(html, "https://oem.example.com/p/UNSEEN-GTIN")
    assert bundle.get("GTIN").value == "0123456789012"
    assert bundle.product_ids.get("gtin") == "0123456789012"
    assert bundle.get("Pack Quantity").value == "25"


def test_labeled_specs_keep_named_columns_after_early_table_rows():
    from extract.labeled_specs import extract_labeled_specs

    junk = "".join(f"<tr><th>Feature {i}</th><td>Value {i}</td></tr>" for i in range(90))
    html = f"""
    <html><body><table>
      {junk}
      <tr><th>Pack Quantity</th><td>25</td></tr>
      <tr><th>GTIN</th><td>0123456789012</td></tr>
      <tr><th>Application</th><td>Metal cutting</td></tr>
      <tr><th>Country Of Origin</th><td>China</td></tr>
    </table></body></html>
    """
    bundle = extract_labeled_specs(html, "https://oem.example.com/p/UNSEEN-COLS")
    assert bundle.get("Pack Quantity").value == "25"
    assert bundle.get("GTIN").value == "0123456789012"
    assert bundle.get("Application").value == "Metal cutting"
    assert bundle.get("Country Of Origin").value == "China"
