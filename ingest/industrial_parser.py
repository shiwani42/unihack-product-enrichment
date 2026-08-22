"""Parse cryptic industrial distributor descriptions into structured evidence."""

import re

from extract.evidence import Evidence, EvidenceBundle

PIPE_PATTERN = re.compile(
    r"(?i)(?:(\d+(?:/\d+)?(?:-\d+/\d+)?)\s*(?:\"|in)?\s+)?"
    r"(coupling|cplg|cpl|elbow|tee|adapter|adpt|nipple|union|bushing|plug|cap|valve|flange)"
    r"(?:\s+(brass|brs|bronze|brz|steel|ss|stainless|pvc|galv|copper|alum|aluminum))?"
    r"(?:\s+(\d+)\s*#)?"
)

DIMENSION_ONLY = re.compile(
    r"(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s*(?:\"|in)\s*[xX×]\s*"
    r"(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s*(?:\"|in)?(?:\s*[xX×]\s*(\d+(?:-\d+/\d+)?(?:\.\d+)?)\s*(?:\"|in)?)?"
)


def _set(bundle: EvidenceBundle, field: str, value: str, uom: str = "", confidence: float = 0.72) -> None:
    if not value:
        return
    bundle.set(
        Evidence(
            field=field,
            value=value,
            uom=uom,
            source_url="input:Part_Desc",
            quote=value[:120],
            extractor="industrial_parser",
            confidence=confidence,
        )
    )


def parse_industrial_desc(part_desc: str) -> EvidenceBundle:
    bundle = EvidenceBundle()
    text = part_desc.strip()
    lower = text.lower()

    pipe = PIPE_PATTERN.search(text)
    if pipe:
        size, fitting, material, pressure = pipe.groups()
        _set(bundle, "Product Type", fitting.title().replace("Cplg", "Coupling"))
        if size:
            _set(bundle, "Size", size if '"' in text or "in" in lower else f'{size}"', "in")
        if material:
            material_map = {"brs": "Brass", "brz": "Bronze", "ss": "Stainless Steel", "galv": "Galvanized", "alum": "Aluminum"}
            _set(bundle, "Material", material_map.get(material.lower(), material.title()))
            _set(bundle, "Color", material_map.get(material.lower(), material.title()))
        if pressure:
            _set(bundle, "Pressure Rating", pressure, "PSI")
        _set(bundle, "Application", "Pipe Fitting")
        return bundle

    dims = DIMENSION_ONLY.search(text)
    if dims:
        parts = [p for p in dims.groups() if p]
        size = " x ".join(f'{p}"' for p in parts)
        _set(bundle, "Size", size, "in")
        _set(bundle, "Length", size, "in")

    if re.search(r"\bmortar\b|\bgrout\b", lower):
        _set(bundle, "Product Type", "Mortar Mix")
        _set(bundle, "Application", "Masonry")
    elif re.search(r"\btrex\b|\bdeck(?:ing)?\b|\bfascia\b|\brail\b|\bgrooved\b", lower):
        _set(bundle, "Product Type", "Composite Decking")
        _set(bundle, "Application", "Decking")
        color = re.search(r"\b(black|white|gray|grey|brown|sand|shell|tiki|firepit)\b", lower)
        if color:
            _set(bundle, "Color", color.group(1).title())
        length = re.search(r"(\d+(?:'\d+)?|\d+(?:\.\d+)?)\s?(?:'|ft|foot)", text, re.I)
        if length:
            _set(bundle, "Length", length.group(1), "ft")
    elif re.search(r"\bwire\b|\bcable\b|\bromex\b|\bthhn\b", lower):
        _set(bundle, "Product Type", "Electrical Wire")
        gauge = re.search(r"\b(\d{1,2})\s?(?:ga|awg|gauge)\b", lower)
        if gauge:
            _set(bundle, "Wire Gauge", gauge.group(1), "AWG")
    elif re.search(r"\btape\b|\belect tape\b", lower):
        _set(bundle, "Product Type", "Electrical Tape")
        width = re.search(r"(\d+(?:\.\d+)?)\s?[xX×]\s?(\d+(?:'\d+)?|\d+(?:\.\d+)?)", text)
        if width:
            _set(bundle, "Width", width.group(1), "in")
            _set(bundle, "Length", width.group(2), "ft")

    grit = re.search(r"\bP(\d{2,3})\b", text)
    if grit:
        _set(bundle, "Grit", f"P{grit.group(1)}")

    return bundle
