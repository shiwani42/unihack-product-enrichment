from classify.taxonomy_matcher import match_taxonomy
from ingest.industrial_parser import parse_industrial_desc


def test_taxonomy_matches_dishwasher():
    match = match_taxonomy("PDSH4816AF Dishwasher SS", "Frigidaire")
    assert match is not None
    assert "Dishwasher" in match.classpath or match.template_id == "built_in_dishwasher"


def test_taxonomy_matches_deck():
    match = match_taxonomy("Trex Transcend Grooved Decking 12'", "")
    assert match is not None
    assert match.template_id == "deck_composite"


def test_industrial_parser_coupling():
    bundle = parse_industrial_desc('3/8 CPLG BRS 150#')
    assert bundle.get("Product Type")
    assert bundle.get("Material")
    assert bundle.get("Pressure Rating")
