from classify.category_router import route_category
from identity.brand_resolver import resolve_identity


def test_downlight_not_dishwasher():
    template = route_category('S11562 Starfish 6" D/W Downlight', "")
    assert template.category_id == "led_lighting"


def test_deck_post_not_electrical_box():
    template = route_category("4x4 Wh Heritage Post Trim RDI", "")
    assert template.category_id == "building_trim"


def test_gilmour_fan_brand_from_desc():
    identity = resolve_identity("51334", '51334 44" Wh Gilmour Fan', "", "")
    assert identity.brand_key == "Gilmour"


def test_hiolit_brand_and_abrasive_route():
    identity = resolve_identity("5B-332-080", '5B-332-080 HIOLIT 5" P80', "", "")
    assert identity.brand_key == "Mirka"
    template = route_category('5B-332-080 HIOLIT 5" P80', identity.brand_key)
    assert template.category_id in {"metal_cutoff_disc", "sanding_abrasive"}
