from app.config import DEFAULT_INPUT
from classify.category_router import route_category
from identity.brand_resolver import resolve_identity
from ingest.csv_io import read_input_rows


def test_every_row_routes_to_a_category():
    rows = read_input_rows(DEFAULT_INPUT)
    for row in rows:
        identity = resolve_identity(
            row["Mfg_Part_Num"],
            row["Part_Desc"],
            row.get("E1_Brand", ""),
            row.get("DIB_Brand", ""),
        )
        template = route_category(row["Part_Desc"], identity.brand_key)
        assert template.category_id


def test_generic_fallback_used_for_unknown_products():
    template = route_category("MISC-123 Widget Adapter", "")
    assert template.category_id == "generic_industrial"
