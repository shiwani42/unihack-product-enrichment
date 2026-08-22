from classify.category_router import CategoryTemplate
from extract.evidence import EvidenceBundle


def apply_template_attributes(row: dict[str, str], template: CategoryTemplate, bundle: EvidenceBundle) -> None:
    for index, label in enumerate(template.attribute_labels, start=1):
        row[f"ATTRIBUTE_LABEL {index}"] = label
        evidence = bundle.get(label)
        if evidence:
            row[f"ATTRIBUTE_VALUE {index}"] = evidence.value
            row[f"ATTRIBUTE_UOM {index}"] = evidence.uom


def apply_taxonomy(row: dict[str, str], template: CategoryTemplate) -> None:
    row["Classpath"] = template.classpath
    row["Dept"] = template.dept
    row["Class"] = template.class_name
    row["Fine"] = template.fine
    row["Product Name"] = template.product_name
