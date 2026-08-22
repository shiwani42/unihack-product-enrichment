import json
import re
from dataclasses import dataclass
from pathlib import Path

from classify.taxonomy_matcher import TaxonomyMatch, match_taxonomy

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
ROUTING_RULES_PATH = Path(__file__).resolve().parent / "routing_rules.json"

APPLIANCE_BRANDS = frozenset({"Frigidaire", "Whirlpool", "GE", "KitchenAid", "LG", "Cafe", "Samsung", "Beko"})
ABRASIVE_BRANDS = frozenset({"Diablo", "Milwaukee", "DEWALT", "3M", "Mirka"})


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
    leaf_id: str = ""
    taxonomy_confidence: float = 0.0


def load_template(category_id: str) -> CategoryTemplate:
    path = TEMPLATE_DIR / f"{category_id}.json"
    if not path.exists():
        path = TEMPLATE_DIR / "generic_industrial.json"
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


def _template_from_taxonomy(match: TaxonomyMatch) -> CategoryTemplate:
    base = load_template(match.template_id)
    return CategoryTemplate(
        category_id=match.template_id,
        classpath=match.classpath,
        dept=match.dept,
        class_name=match.class_name,
        fine=match.fine,
        product_name=match.product_name,
        attribute_labels=base.attribute_labels,
        description_rules=base.description_rules,
        leaf_id=match.leaf_id,
        taxonomy_confidence=match.confidence,
    )


def _load_routing_rules() -> list[dict]:
    return json.loads(ROUTING_RULES_PATH.read_text(encoding="utf-8"))


def _is_dishwasher_desc(part_desc: str) -> bool:
    text = part_desc.lower()
    if re.search(r"downlight|under.?cabinet|mortar|post trim|post cap|post sleeve|attic", text):
        return False
    return bool(re.search(r"\bdishwasher\b", text, re.I))


def _matches_rule(part_desc: str, brand_key: str, rule: dict) -> bool:
    if rule.get("fallback"):
        return False

    template = rule.get("template", "")
    text = part_desc.lower()

    if template == "built_in_dishwasher":
        if not _is_dishwasher_desc(part_desc):
            if brand_key in APPLIANCE_BRANDS and re.search(r"\bdishwasher\b", part_desc, re.I):
                return True
            return False
        return True

    if template == "electrical_box":
        if re.search(r"post trim|post cap|post sleeve|attic access|heritage post|elite post|blank post", text):
            return False
        for pattern in rule.get("patterns", []):
            if re.search(pattern, part_desc, re.I):
                return True
        return False

    if template == "ceiling_fan":
        if re.search(r"gilmour", text) and not re.search(r"hunter", text):
            return bool(re.search(r"fan", text, re.I))
        for pattern in rule.get("patterns", []):
            if pattern.endswith("$"):
                if re.search(pattern, text, re.I):
                    return True
            elif re.search(pattern, part_desc, re.I):
                return True
        return False

    if template == "cooking_range":
        if re.search(r"mortar|grille|damper|filter", text):
            return False
        for pattern in rule.get("patterns", []):
            if re.search(pattern, part_desc, re.I):
                return True
        return False

    for pattern in rule.get("patterns", []):
        if pattern.endswith("$"):
            if re.search(pattern, text, re.I):
                return True
        elif re.search(pattern, part_desc, re.I):
            return True

    if brand_key in ABRASIVE_BRANDS and re.search(r"\d+\s?(?:\"|in)", part_desc):
        if template in {"metal_cutoff_disc", "grinding_wheel", "sanding_abrasive"}:
            return True

    return False


def route_category(part_desc: str, brand_key: str) -> CategoryTemplate:
    tax = match_taxonomy(part_desc, brand_key)
    if tax and tax.confidence >= 0.55:
        return _template_from_taxonomy(tax)

    rules = _load_routing_rules()
    fallback_id = "generic_industrial"
    for rule in rules:
        if rule.get("fallback"):
            fallback_id = rule["template"]
            continue
        if _matches_rule(part_desc, brand_key, rule):
            template = load_template(rule["template"])
            if tax and tax.template_id == template.category_id:
                return _template_from_taxonomy(tax)
            return template
    return load_template(fallback_id)
