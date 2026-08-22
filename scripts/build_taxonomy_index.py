import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "classify" / "templates"
OUTPUT = ROOT / "data" / "taxonomy" / "leaves.json"

EXTRA_LEAVES = [
    {
        "leaf_id": "composite_decking_trex",
        "classpath": "Building Materials>Decking & Railing>Composite Decking",
        "dept": "Building Materials",
        "class": "Decking & Railing",
        "fine": "Composite Decking",
        "product_name": "Composite Decking Board",
        "template_id": "deck_composite",
        "keywords": ["trex", "deck", "decking", "transcend", "enhance", "select", "lineage", "grooved", "fascia", "rail", "azek"],
        "patterns": [r"\btrex\b", r"\bdeck(?:ing)?\b", r"\bfascia\b", r"\bgrooved\b"],
    },
    {
        "leaf_id": "pipe_fitting_coupling",
        "classpath": "Plumbing>Pipe & Fittings>Couplings",
        "dept": "Plumbing",
        "class": "Pipe & Fittings",
        "fine": "Couplings",
        "product_name": "Pipe Coupling",
        "template_id": "pipe_fitting",
        "keywords": ["coupling", "cplg", "cpl", "elbow", "tee", "adapter", "nipple", "npt", "fnpt", "brass", "brs"],
        "patterns": [r"\bcplg\b", r"\bcoupling\b", r"\belbow\b", r"\b\d+\s*#"],
    },
    {
        "leaf_id": "electrical_wire",
        "classpath": "Electrical>Wire & Cable>Building Wire",
        "dept": "Electrical",
        "class": "Wire & Cable",
        "fine": "Building Wire",
        "product_name": "Electrical Wire",
        "template_id": "wire_cable",
        "keywords": ["wire", "cable", "romex", "thhn", "southwire", "gauge", "awg"],
        "patterns": [r"\bwire\b", r"\bcable\b", r"\bawg\b"],
        "brands": ["Southwire"],
    },
    {
        "leaf_id": "building_trim_post",
        "classpath": "Building Materials>Exterior Trim>Post Components",
        "dept": "Building Materials",
        "class": "Exterior Trim",
        "fine": "Post Components",
        "product_name": "Deck Post Trim",
        "template_id": "building_trim",
        "keywords": ["post trim", "post cap", "post sleeve", "heritage post", "elite post", "blank post"],
        "patterns": [r"post trim", r"post cap", r"post sleeve"],
    },
    {
        "leaf_id": "grinding_wheel",
        "classpath": "Tools & Hardware>Abrasives>Grinding Wheels",
        "dept": "Tools & Hardware",
        "class": "Abrasives",
        "fine": "Grinding Wheels",
        "product_name": "Grinding Wheel",
        "template_id": "grinding_wheel",
        "keywords": ["grinding wheel", "cut and grind", "dual metal", "masonry grinding"],
        "patterns": [r"grind(?:ing)? wheel", r"cut and grind", r"dual metal cut"],
        "brands": ["Milwaukee", "Diablo"],
    },
    {
        "leaf_id": "sanding_abrasive",
        "classpath": "Tools & Hardware>Abrasives>Sanding Supplies",
        "dept": "Tools & Hardware",
        "class": "Abrasives",
        "fine": "Sanding Supplies",
        "product_name": "Sanding Abrasive",
        "template_id": "sanding_abrasive",
        "keywords": ["sanding belt", "sandpaper", "sanding sponge", "stikit", "sanding film", "sanding disc"],
        "patterns": [r"sanding belt", r"sandpaper", r"sanding sponge", r"sanding film"],
        "brands": ["3M", "Diablo", "Mirka"],
    },
    {
        "leaf_id": "mortar_mix",
        "classpath": "Building Materials>Masonry>Mortar & Grout",
        "dept": "Building Materials",
        "class": "Masonry",
        "fine": "Mortar & Grout",
        "product_name": "Mortar Mix",
        "template_id": "generic_industrial",
        "keywords": ["mortar", "grout", "thinset"],
        "patterns": [r"\bmortar\b", r"\bgrout\b"],
    },
    {
        "leaf_id": "electrical_tape",
        "classpath": "Electrical>Electrical Tape>Vinyl Tape",
        "dept": "Electrical",
        "class": "Electrical Tape",
        "fine": "Vinyl Tape",
        "product_name": "Electrical Tape",
        "template_id": "wire_cable",
        "keywords": ["elect tape", "electrical tape", "vinyl tape", "emseal"],
        "patterns": [r"elect tape", r"electrical tape", r"vinyl.*tape"],
    },
]


def main() -> None:
    leaves: list[dict] = []
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        keywords = [data["product_name"].lower(), data["fine"].lower(), data["class"].lower()]
        keywords.extend(re.findall(r"[a-z]{3,}", data["classpath"].lower()))
        leaves.append(
            {
                "leaf_id": data["category_id"],
                "classpath": data["classpath"],
                "dept": data["dept"],
                "class": data["class"],
                "fine": data["fine"],
                "product_name": data["product_name"],
                "template_id": data["category_id"],
                "keywords": sorted(set(keywords)),
                "patterns": [],
            }
        )

    leaves.extend(EXTRA_LEAVES)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(leaves, indent=2), encoding="utf-8")
    print(f"Wrote {len(leaves)} taxonomy leaves to {OUTPUT}")


if __name__ == "__main__":
    main()
