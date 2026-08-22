import json
import re
from dataclasses import dataclass
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@dataclass
class CategoryTemplate:
    category_id: str
    classpath: str
    dept: str
    class_name: str
    fine: str
    product_name: str
    attribute_labels: list[str]
    description_rules: dict[str, int]


def load_template(category_id: str) -> CategoryTemplate:
    path = TEMPLATE_DIR / f"{category_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return CategoryTemplate(
        category_id=data["category_id"],
        classpath=data["classpath"],
        dept=data["dept"],
        class_name=data["class"],
        fine=data["fine"],
        product_name=data["product_name"],
        attribute_labels=data["attribute_labels"],
        description_rules=data.get("description_rules", {}),
    )


def route_category(part_desc: str, brand_key: str) -> CategoryTemplate | None:
    text = part_desc.lower()
    if "dishwasher" in text:
        return load_template("built_in_dishwasher")
    if brand_key in {"Frigidaire", "Whirlpool", "GE", "KitchenAid", "LG", "Cafe"} and re.search(
        r"dishwasher|d/w", text, re.I
    ):
        return load_template("built_in_dishwasher")
    if re.search(r"cut.?off disc|metal cut|sand(ing)? belt|abrasive disc", part_desc, re.I):
        return load_template("metal_cutoff_disc")
    if brand_key in {"Diablo", "Milwaukee", "DEWALT"} and re.search(r"\d+\s?(?:\"|in)", part_desc):
        return load_template("metal_cutoff_disc")
    return None
