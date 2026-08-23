"""Labeled spec pairs from any manufacturer PDP: tables, definition lists, spec widgets.

Regex catalogs in spec_patterns.json only fire for fields we have already seen.
A judge SKU ships whatever labels the brand uses (Wheel Type, Grit Size, Bore).
Those still have to become evidence. High-value named columns (GTIN, pack qty,
Application) are kept even when earlier tables already filled the pair cap.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from extract.evidence import Evidence, EvidenceBundle

_SKIP_LABELS = frozenset(
    {
        "cart",
        "menu",
        "search",
        "account",
        "sign in",
        "log in",
        "login",
        "email",
        "password",
        "cookie",
        "subscribe",
        "follow",
        "share",
        "qty",
        "price",
        "compare",
        "wishlist",
        "language",
        "currency",
        "shop",
        "home",
        "filter",
        "sort",
        "availability",
        "shipping",
        "item",
        "id",
        "url",
        "image",
        "description",
        "name",
        "title",
        "brand",
        "category",
    }
)
_KEEP_LABELS = frozenset(
    {
        "sku",
        "quantity",
        "pack quantity",
        "pack qty",
        "package quantity",
        "gtin",
        "upc",
        "ean",
        "unspsc",
        "application",
        "includes",
        "with",
        "weight",
        "warranty",
        "country of origin",
        "prop 65",
        "proposition 65",
    }
)
_SKIP_VALUES = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "none",
        "select",
        "choose",
        "learn more",
        "click here",
        "view",
        "yes/no",
    }
)
_SPEC_CLASS = re.compile(
    r"spec|attribute|detail|techsheet|tech-spec|facts|product-info|pdp|datasheet",
    re.I,
)
_PAIR = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9][A-Za-z0-9 /&+\-]{0,42})\s*[:\-–|]\s+(.{1,80}?)\s*$"
)
_UOM_TAIL = re.compile(
    r"^(?P<val>.+?)\s+(?P<uom>in|inch|inches|mm|cm|lb|lbs|kg|oz|rpm|v|volts?|a|amps?|w|watts?)$",
    re.I,
)
_PRIORITY_LABELS = frozenset(
    {
        "pack quantity",
        "pack qty",
        "package quantity",
        "gtin",
        "upc",
        "ean",
        "unspsc",
        "application",
        "includes",
        "with",
        "prop 65",
        "proposition 65",
        "country of origin",
        "weight",
        "net weight",
        "warranty",
        "diameter",
        "wheel diameter",
        "arbor size",
        "thickness",
        "maximum rpm",
        "grit",
        "length",
        "height",
        "width",
        "volume",
    }
)
_MAX_PAIRS = 80
_HTML_CAP = 400_000


def _clean_label(text: str) -> str:
    label = re.sub(r"\s+", " ", (text or "").strip()).rstrip(":")
    return label[:48]


def _clean_value(text: str) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    return value[:80]


def _usable_pair(label: str, value: str) -> bool:
    if not label or not value:
        return False
    key = label.lower().strip()
    if key in _SKIP_LABELS and key not in _KEEP_LABELS:
        return False
    if value.lower() in _SKIP_VALUES:
        return False
    if len(label) < 2 or len(value) < 1:
        return False
    if re.search(r"https?://", value, re.I):
        return False
    if value.lower() in {key, "true", "false", "null"}:
        return False
    if len(label.split()) > 8:
        return False
    if not re.search(r"[A-Za-z]", label):
        return False
    return True


def _split_uom(value: str) -> tuple[str, str]:
    match = _UOM_TAIL.match(value or "")
    if not match or len((value or "").split()) > 4:
        return value, ""
    return match.group("val").strip(), match.group("uom").strip()


def _two_cell_text(cells) -> tuple[str, str] | None:
    texts = [_clean_label(cell.get_text(" ", strip=True)) for cell in cells]
    if len(texts) < 2:
        return None
    return texts[0], _clean_value(cells[1].get_text(" ", strip=True))


def extract_labeled_specs(html: str, url: str) -> EvidenceBundle:
    bundle = EvidenceBundle(mfr_url=url)
    raw = html or ""
    if len(raw) > _HTML_CAP:
        raw = raw[:320_000] + raw[-80_000:]
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
        tag.decompose()

    pairs: list[tuple[str, str, str]] = []

    def collect(label: str, value: str, quote: str) -> None:
        if not _usable_pair(label, value):
            return
        pairs.append((label, value, quote[:180]))

    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt", recursive=False) or dl.find_all("dt")
        dds = dl.find_all("dd", recursive=False) or dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            label = _clean_label(dt.get_text(" ", strip=True))
            value = _clean_value(dd.get_text(" ", strip=True))
            collect(label, value, f"{label}: {value}")

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            pair = _two_cell_text(cells)
            if not pair:
                continue
            label, value = pair
            if len(cells) > 3:
                continue
            collect(label, value, f"{label}: {value}")

    for node in soup.find_all(class_=_SPEC_CLASS):
        kids = [child for child in node.find_all(recursive=False) if getattr(child, "get_text", None)]
        if len(kids) == 2:
            label = _clean_label(kids[0].get_text(" ", strip=True))
            value = _clean_value(kids[1].get_text(" ", strip=True))
            collect(label, value, f"{label}: {value}")
        text = node.get_text("\n", strip=True)
        for line in text.splitlines():
            match = _PAIR.match(line)
            if match:
                collect(_clean_label(match.group(1)), _clean_value(match.group(2)), line)

    ranked = sorted(
        enumerate(pairs),
        key=lambda item: (0 if item[1][0].lower().strip() in _PRIORITY_LABELS else 1, item[0]),
    )
    seen: set[str] = set()
    for _, (label, value, quote) in ranked:
        key = label.lower().strip()
        if key in seen or len(bundle.items) >= _MAX_PAIRS:
            continue
        seen.add(key)
        core, uom = _split_uom(value)
        bundle.set(
            Evidence(
                field=label,
                value=core or value,
                uom=uom,
                source_url=url,
                quote=quote,
                extractor="labeled_html",
                confidence=0.8,
            )
        )
    return bundle
