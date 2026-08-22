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
