from classify.category_router import CategoryTemplate
from extract.evidence import EvidenceBundle
from normalize.aliases import _load_aliases, pick_evidence_for_label

_MAX_ATTR_SLOTS = 50

_NAMED_FIELDS = {
    "application": "Application",
    "includes": "Includes",
    "with": "With",
    "prop 65": "Prop 65",
    "prop65": "Prop 65",
    "proposition 65": "Prop 65",
    "standard/approvals": "Standard/Approvals",
    "approvals": "Standard/Approvals",
    "warranty": "Warranty",
    "country of origin": "Country Of Origin",
    "origin": "Country Of Origin",
    "upc": "UPC",
    "ean": "EAN",
    "gtin": "GTIN",
    "gtin13": "GTIN",
    "gtin12": "UPC",
    "unspsc": "UNSPSC",
    "alternate part number": "ALTERNATE_PART_NUMBER",
    "alternate part": "ALTERNATE_PART_NUMBER",
    "model": "ALTERNATE_PART_NUMBER",
}

_DIM_FIELDS = {
    "length": ("LENGTH", "LENGTH_UOM"),
    "height": ("HEIGHT", "HEIGHT_UOM"),
    "width": ("WIDTH", "WIDTH_UOM"),
    "weight": ("WEIGHT", "WEIGHT_UOM"),
    "volume": ("VOLUME", "VOLUME_UOM"),
}

_PACK_FIELDS = frozenset(
    {
        "pack quantity",
        "pack qty",
        "package quantity",
        "selling qty",
        "pieces per pack",
        "qty per pack",
    }
)
_WEIGHT_FIELDS = frozenset({"weight", "net weight", "item weight", "product weight"})
_LENGTH_FIELDS = frozenset({"length", "overall length", "item length"})


def _norm_label(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _match_evidence(bundle: EvidenceBundle, label: str, aliases: dict[str, list[str]]):
    return pick_evidence_for_label(bundle, label, aliases)


def _fill_named_column(row: dict[str, str], column: str, value: str, uom: str = "") -> None:
    if not column or not (value or "").strip():
        return
    if not (row.get(column) or "").strip():
        row[column] = value.strip()
    if uom and column in {"LENGTH", "HEIGHT", "WIDTH", "WEIGHT", "VOLUME"}:
        uom_col = f"{column}_UOM"
        if not (row.get(uom_col) or "").strip():
            row[uom_col] = uom.strip()


def apply_template_attributes(row: dict[str, str], template: CategoryTemplate, bundle: EvidenceBundle) -> None:
    """Fill template slots, named delivery columns, then leftover attribute slots.

    Unilog always has 50 attribute triples. Templates only name the slots that
    category usually has. Extra manufacturer specs go into unused slots, and
    matching named columns (Application, GTIN, WEIGHT, …) are filled too.
    """
    aliases = _load_aliases()
    used: set[str] = set()
    for index, label in enumerate(template.attribute_labels, start=1):
        row[f"ATTRIBUTE_LABEL {index}"] = label
        evidence = _match_evidence(bundle, label, aliases)
        if evidence and (evidence.value or "").strip():
            row[f"ATTRIBUTE_VALUE {index}"] = evidence.value
            row[f"ATTRIBUTE_UOM {index}"] = evidence.uom or ""
            used.add(_norm_label(label))
            used.add(_norm_label(evidence.field))

    for item in bundle.items:
        field = _norm_label(item.field)
        value = (item.value or "").strip()
        if not field or not value:
            continue
        named = _NAMED_FIELDS.get(field)
        if named == "ALTERNATE_PART_NUMBER":
            mpn = (row.get("MANUFACTURER_PART_NUMBER") or row.get("Mfg_Part_Num") or "").strip()
            if mpn and value.lower() == mpn.lower():
                named = ""
        if named:
            _fill_named_column(row, named, value, item.uom)
            used.add(field)
        dim = _DIM_FIELDS.get(field)
        if not dim and field in _WEIGHT_FIELDS:
            dim = ("WEIGHT", "WEIGHT_UOM")
        if not dim and field in _LENGTH_FIELDS:
            dim = ("LENGTH", "LENGTH_UOM")
        if dim:
            _fill_named_column(row, dim[0], value, item.uom)
            used.add(field)
        if field in _PACK_FIELDS:
            _fill_named_column(row, "Selling Qty", value)
            if item.uom:
                _fill_named_column(row, "Selling UOM", item.uom)
            if not (row.get("Standard Packaging Information") or "").strip():
                row["Standard Packaging Information"] = f"Pack of {value}"
            used.add(field)

    origin = bundle.product_ids.get("countryoforigin") or bundle.product_ids.get("country") or ""
    if origin:
        _fill_named_column(row, "Country Of Origin", origin)
    if bundle.approvals:
        _fill_named_column(row, "Standard/Approvals", bundle.approvals)
    if bundle.warranty:
        _fill_named_column(row, "Warranty", bundle.warranty)

    slot = len(template.attribute_labels) + 1
    for item in bundle.items:
        if slot > _MAX_ATTR_SLOTS:
            break
        label = (item.field or "").strip()
        value = (item.value or "").strip()
        if not label or not value:
            continue
        key = _norm_label(label)
        if key in used:
            continue
        row[f"ATTRIBUTE_LABEL {slot}"] = label
        row[f"ATTRIBUTE_VALUE {slot}"] = value
        row[f"ATTRIBUTE_UOM {slot}"] = item.uom or ""
        used.add(key)
        slot += 1


def apply_taxonomy(row: dict[str, str], template: CategoryTemplate) -> None:
    row["Classpath"] = template.classpath
    row["Dept"] = template.dept
    row["Class"] = template.class_name
    row["Fine"] = template.fine
    row["Product Name"] = template.product_name
