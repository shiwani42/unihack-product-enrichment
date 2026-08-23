"""Reviewer hints from the inspect drawer: a known URL, a missing spec, a flag.

The 1000-SKU run taught the pipeline by patching code. A person looking at one
row often already knows the manufacturer page or that Size=1440 is image width.
Those notes are stored here (not a SKU allowlist): the URL is remembered like
any live hit, overrides refill the same MPN on a later enrich, and repeated
flags become rejected values / storefront hosts for later parts.
"""

from __future__ import annotations

import ipaddress
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx

from extract.evidence import Evidence, EvidenceBundle
from io_utils import atomic_write_text
from normalize.values import cleanse_attribute

REVIEWER_FILE = Path(__file__).resolve().parents[1] / "data" / "reviewer_memory.json"
MAX_FLAGS = 300
MAX_OVERRIDE_MPNS = 400
GLOBAL_REJECT_AFTER = 2
REASON_MAX = 400
VALUE_MAX = 200

_DEALER_REASON = re.compile(
    r"dealer|storefront|wrong (site|page|product|host)|not (the )?manufacturer|competitor|reseller",
    re.I,
)
_PIXEL_REASON = re.compile(r"pixel|og:image|image width|open graph|css width", re.I)

_lock = threading.Lock()
_cache: dict | None = None


def _reset_cache() -> None:
    global _cache
    _cache = None


def _read() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    empty = {"rejected": {}, "overrides": {}, "urls": {}, "flags": []}
    if not REVIEWER_FILE.exists():
        _cache = empty
        return _cache
    try:
        payload = json.loads(REVIEWER_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        _cache = empty
        return _cache
    if not isinstance(payload, dict):
        _cache = empty
        return _cache
    _cache = {
        "rejected": payload.get("rejected") if isinstance(payload.get("rejected"), dict) else {},
        "overrides": payload.get("overrides") if isinstance(payload.get("overrides"), dict) else {},
        "urls": payload.get("urls") if isinstance(payload.get("urls"), dict) else {},
        "flags": payload.get("flags") if isinstance(payload.get("flags"), list) else [],
    }
    return _cache


def _write(payload: dict) -> None:
    REVIEWER_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        REVIEWER_FILE,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def snapshot_payload() -> dict:
    return json.loads(json.dumps(_read()))


def restore_payload(payload: dict | None) -> None:
    if not isinstance(payload, dict):
        return
    global _cache
    with _lock:
        merged = {
            "rejected": payload.get("rejected") if isinstance(payload.get("rejected"), dict) else {},
            "overrides": payload.get("overrides") if isinstance(payload.get("overrides"), dict) else {},
            "urls": payload.get("urls") if isinstance(payload.get("urls"), dict) else {},
            "flags": payload.get("flags") if isinstance(payload.get("flags"), list) else [],
        }
        try:
            _write(merged)
        except OSError:
            return
        _cache = merged


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _reject_key(field: str, value: str) -> str:
    return f"{_norm(field)}|{_norm(value)}"


def is_rejected_value(field: str, value: str) -> bool:
    rec = _read().get("rejected") or {}
    item = rec.get(_reject_key(field, value))
    if not isinstance(item, dict):
        return False
    if item.get("global"):
        return True
    return int(item.get("n") or 0) >= GLOBAL_REJECT_AFTER


def hint_url_allowed(url: str) -> str:
    """Return a cleaned http(s) URL, or empty if it should not be fetched."""
    raw = (url or "").strip()
    if not raw or len(raw) > 2000:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in {"http", "https"}:
        return ""
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return ""
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return ""
    except ValueError:
        pass
    from sources.finder import is_shopping_or_noise_url
    from sources.page_ok import is_error_url

    rebuilt = parsed.geturl()
    if is_shopping_or_noise_url(rebuilt) or is_error_url(rebuilt):
        return ""
    return rebuilt


def fetch_hint_html(url: str) -> tuple[int, str, str]:
    cleaned = hint_url_allowed(url)
    if not cleaned:
        return 0, "", url
    from sources.finder import is_shopping_or_noise_url
    from sources.web_search import BROWSER_HEADERS

    timeout = httpx.Timeout(connect=3.0, read=18.0, write=5.0, pool=2.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=BROWSER_HEADERS) as client:
            response = client.get(cleaned)
    except httpx.HTTPError:
        return 0, "", cleaned
    final = str(response.url)
    if is_shopping_or_noise_url(final):
        return 0, "", cleaned
    return response.status_code, response.text or "", final


def ingest_hint_url(
    url: str,
    mpn: str,
    names: list[str] | None = None,
    domains: list[str] | None = None,
) -> EvidenceBundle:
    """Fetch a reviewer-supplied page and extract specs. Shopping stays blocked."""
    from extract.html_specs import extract_from_html
    from extract.merge import merge_bundles
    from extract.page_state import extract_page_state
    from extract.pdf_specs import extract_from_pdf_bytes
    from extract.structured import extract_structured_data
    from sources.domain_discovery import host_matches_names
    from sources.finder import is_distributor_url, is_search_url, looks_like_dealer_storefront
    from sources.learned_hosts import learn_from_page
    from sources.page_ok import is_usable_page, looks_like_pdf

    bundle = EvidenceBundle()
    cleaned = hint_url_allowed(url)
    if not cleaned:
        return bundle
    status, html, final = fetch_hint_html(cleaned)
    use_url = final or cleaned
    if not is_usable_page(status, html, use_url):
        return bundle
    names = [name for name in (names or []) if name]
    host_domains = list(domains or [])
    parsed = urlparse(use_url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    dealer = looks_like_dealer_storefront(use_url) or is_distributor_url(use_url)
    if host and not dealer:
        host_domains = list(dict.fromkeys(host_domains + [host]))
    if looks_like_pdf(html):
        try:
            page = extract_from_pdf_bytes(html.encode("latin-1", errors="replace"), use_url)
        except Exception:
            page = EvidenceBundle()
    else:
        page = merge_bundles(
            extract_from_html(html, use_url),
            extract_structured_data(html, use_url),
            extract_page_state(html, use_url),
        )
    learn_from_page(use_url, html, page, names)
    if dealer:
        page.marketing = ""
        page.features = []
        page.image_urls = []
        page.mfr_url = ""
        if use_url not in page.ref_urls:
            page.ref_urls.append(use_url)
    else:
        page.mfr_url = "" if is_search_url(use_url) else use_url
        if is_search_url(use_url) and use_url not in page.ref_urls:
            page.ref_urls.append(use_url)
        if page.mfr_url and names and not host_matches_names(host, names) and not host_domains:
            page.ref_urls = list(dict.fromkeys([page.mfr_url] + page.ref_urls))
            page.mfr_url = ""
    return page


def _append_ref_urls(row: dict[str, str], urls: list[str]) -> None:
    existing = [row.get("MFR URL") or ""]
    existing.extend(row.get(f"Ref URL {i}") or "" for i in range(1, 6))
    seen = {item for item in existing if item}
    for url in urls:
        raw = (url or "").strip()
        if not raw.startswith("http") or raw in seen:
            continue
        if not (row.get("MFR URL") or "").strip() and raw:
            from sources.finder import is_distributor_url, is_search_url, looks_like_dealer_storefront

            if not is_search_url(raw) and not looks_like_dealer_storefront(raw) and not is_distributor_url(raw):
                row["MFR URL"] = raw
                seen.add(raw)
                continue
        for index in range(1, 6):
            key = f"Ref URL {index}"
            if not (row.get(key) or "").strip():
                row[key] = raw
                seen.add(raw)
                break


def _set_attribute(row: dict[str, str], label: str, value: str, uom: str, category_id: str, mpn: str) -> bool:
    cleaned, unit = cleanse_attribute(label, value, uom or "", category_id or "generic_industrial", mpn=mpn)
    if not cleaned:
        return False
    want = _norm(label)
    slot = None
    empty = None
    for index in range(1, 51):
        current = _norm(row.get(f"ATTRIBUTE_LABEL {index}") or "")
        filled = (row.get(f"ATTRIBUTE_VALUE {index}") or "").strip()
        if current == want:
            slot = index
            break
        if empty is None and not filled and not current:
            empty = index
    target = slot or empty
    if not target:
        return False
    row[f"ATTRIBUTE_LABEL {target}"] = label.strip()
    row[f"ATTRIBUTE_VALUE {target}"] = cleaned
    row[f"ATTRIBUTE_UOM {target}"] = unit
    return True


def _clear_attribute(row: dict[str, str], label: str, value: str = "") -> bool:
    want = _norm(label)
    want_val = _norm(value)
    cleared = False
    for index in range(1, 51):
        current = _norm(row.get(f"ATTRIBUTE_LABEL {index}") or "")
        if current != want:
            continue
        current_val = _norm(row.get(f"ATTRIBUTE_VALUE {index}") or "")
        if want_val and current_val and current_val != want_val:
            continue
        row[f"ATTRIBUTE_VALUE {index}"] = ""
        row[f"ATTRIBUTE_UOM {index}"] = ""
        cleared = True
    return cleared


def apply_saved_overrides(row: dict[str, str], mpn: str) -> None:
    items = (_read().get("overrides") or {}).get(mpn) or []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        _set_attribute(
            row,
            str(item.get("label") or ""),
            str(item.get("value") or ""),
            str(item.get("uom") or ""),
            "generic_industrial",
            mpn,
        )
    urls = (_read().get("urls") or {}).get(mpn) or []
    if isinstance(urls, list):
        _append_ref_urls(row, [str(item) for item in urls])


def _remember_override(mpn: str, label: str, value: str, uom: str) -> None:
    global _cache
    with _lock:
        payload = _read()
        bucket = payload.setdefault("overrides", {}).setdefault(mpn, [])
        if not isinstance(bucket, list):
            bucket = []
            payload["overrides"][mpn] = bucket
        key = _norm(label)
        bucket[:] = [item for item in bucket if isinstance(item, dict) and _norm(item.get("label") or "") != key]
        bucket.append({"label": label.strip(), "value": value.strip(), "uom": (uom or "").strip()})
        if len(payload["overrides"]) > MAX_OVERRIDE_MPNS:
            extra = list(payload["overrides"])[: len(payload["overrides"]) - MAX_OVERRIDE_MPNS]
            for old in extra:
                payload["overrides"].pop(old, None)
        try:
            _write(payload)
        except OSError:
            return
        _cache = payload


def _remember_url(mpn: str, url: str) -> None:
    global _cache
    with _lock:
        payload = _read()
        bucket = payload.setdefault("urls", {}).setdefault(mpn, [])
        if not isinstance(bucket, list):
            bucket = []
            payload["urls"][mpn] = bucket
        if url and url not in bucket:
            bucket.append(url)
        try:
            _write(payload)
        except OSError:
            return
        _cache = payload
    from sources.known_urls import remember_urls

    remember_urls(mpn, [url])


def _auto_global(field: str, value: str, reason: str) -> bool:
    from normalize.values import _junk_spec_value, _plausible_size

    if _junk_spec_value(value):
        return True
    if _PIXEL_REASON.search(reason or ""):
        return True
    if _norm(field) in {"size", "width", "height"} and not _plausible_size(value):
        return True
    return False


def note_flag(mpn: str, field: str, value: str, reason: str, source_url: str = "") -> None:
    global _cache
    reason = (reason or "").strip()[:REASON_MAX]
    field = (field or "").strip()[:80]
    value = (value or "").strip()[:VALUE_MAX]
    if not field:
        return
    key = _reject_key(field, value)
    with _lock:
        payload = _read()
        rejected = payload.setdefault("rejected", {})
        rec = rejected.get(key) if isinstance(rejected.get(key), dict) else {"field": field, "value": value, "n": 0, "reason": reason}
        rec["n"] = int(rec.get("n") or 0) + 1
        rec["reason"] = reason or rec.get("reason") or ""
        rec["global"] = bool(rec.get("global")) or _auto_global(field, value, reason) or rec["n"] >= GLOBAL_REJECT_AFTER
        rejected[key] = rec
        flags = payload.setdefault("flags", [])
        flags.append({"mpn": mpn, "field": field, "value": value, "reason": reason, "url": source_url})
        payload["flags"] = flags[-MAX_FLAGS:]
        overrides = payload.get("overrides") or {}
        if mpn in overrides and isinstance(overrides[mpn], list):
            overrides[mpn] = [
                item
                for item in overrides[mpn]
                if not (isinstance(item, dict) and _norm(item.get("label") or "") == _norm(field))
            ]
        try:
            _write(payload)
        except OSError:
            return
        _cache = payload
    if _DEALER_REASON.search(reason) and source_url:
        from sources.learned_hosts import note_storefront_host

        note_storefront_host(source_url)


def hydrate_row_from_preview(preview: dict, headers: list[str]) -> dict[str, str]:
    from ingest.csv_io import empty_output_row

    row = empty_output_row(headers)
    for source in (preview.get("input") or {}, preview.get("identity") or {}, preview.get("taxonomy") or {}):
        if isinstance(source, dict):
            for key, value in source.items():
                if key in row and value:
                    row[key] = str(value)
    for spec in preview.get("specs") or []:
        if not isinstance(spec, dict):
            continue
        index = int(spec.get("slot") or 0)
        if 1 <= index <= 50:
            row[f"ATTRIBUTE_LABEL {index}"] = str(spec.get("label") or "")
            row[f"ATTRIBUTE_VALUE {index}"] = str(spec.get("value") or "")
            row[f"ATTRIBUTE_UOM {index}"] = str(spec.get("uom") or "")
    for item in preview.get("descriptions_list") or []:
        if isinstance(item, dict) and item.get("key"):
            row[str(item["key"])] = str(item.get("value") or "")
    for index, feature in enumerate(preview.get("features") or [], start=1):
        if index > 20:
            break
        row[f"ITEM_FEATURES_{index}"] = str(feature)
    for key, url in (preview.get("sources") or {}).items():
        if key in row and url:
            row[key] = str(url)
    for asset in preview.get("assets") or []:
        if isinstance(asset, dict) and asset.get("field"):
            row[str(asset["field"])] = str(asset.get("filename") or "")
    return row


def contribute(
    *,
    mpn: str,
    preview: dict | None,
    row: dict[str, str] | None,
    headers: list[str],
    url: str = "",
    attributes: list[dict] | None = None,
    flags: list[dict] | None = None,
    names: list[str] | None = None,
    domains: list[str] | None = None,
    category_id: str = "",
) -> dict:
    """Apply a reviewer URL, typed specs, and/or flags to one catalog row."""
    from classify.category_router import load_template
    from compose.assets import apply_asset_fields
    from extract.merge import merge_bundles
    from normalize.mapper import apply_template_attributes
    from normalize.values import cleanse_output_row
    from sources.learned_hosts import apply_run_lessons
    from validate.rules import overall_confidence, validate_row

    working = dict(row) if row else hydrate_row_from_preview(preview or {}, headers)
    mpn = (mpn or working.get("Mfg_Part_Num") or "").strip()
    working["Mfg_Part_Num"] = mpn
    working["MANUFACTURER_PART_NUMBER"] = working.get("MANUFACTURER_PART_NUMBER") or mpn
    category_id = category_id or (preview or {}).get("category_id") or "generic_industrial"
    template = load_template(category_id)
    filled_before = {
        working.get(f"ATTRIBUTE_LABEL {i}")
        for i in range(1, 51)
        if (working.get(f"ATTRIBUTE_VALUE {i}") or "").strip()
    }
    messages: list[str] = []
    bundle = EvidenceBundle()
    cleaned_url = hint_url_allowed(url) if url else ""
    if url and not cleaned_url:
        messages.append("That link cannot be used (shopping, local, or invalid).")
    elif cleaned_url:
        _remember_url(mpn, cleaned_url)
        bundle = ingest_hint_url(cleaned_url, mpn, names=names, domains=domains)
        apply_run_lessons(bundle, names)
        if bundle.items or bundle.mfr_url or bundle.ref_urls:
            apply_template_attributes(working, template, bundle, only_empty=True)
            if bundle.mfr_url:
                _append_ref_urls(working, [bundle.mfr_url])
            _append_ref_urls(working, bundle.ref_urls)
            apply_asset_fields(working, mpn, bundle)
            added = sum(
                1
                for i in range(1, 51)
                if (working.get(f"ATTRIBUTE_VALUE {i}") or "").strip()
                and working.get(f"ATTRIBUTE_LABEL {i}") not in filled_before
            )
            if added or bundle.mfr_url or bundle.ref_urls:
                messages.append("Fetched the page and kept it for later SKUs on this brand.")
            else:
                messages.append("Saved the link, but that page did not add new specs.")
        else:
            messages.append("Saved the link for later runs; the page did not return specs this time.")

    for flag in flags or []:
        if not isinstance(flag, dict):
            continue
        label = str(flag.get("label") or "").strip()
        value = str(flag.get("value") or "").strip()
        reason = str(flag.get("reason") or "").strip()
        source = str(flag.get("source") or flag.get("url") or "")
        if not label or not reason:
            continue
        note_flag(mpn, label, value, reason, source)
        _clear_attribute(working, label, value)
        messages.append(f"Flagged {label}.")

    for item in attributes or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:80]
        value = str(item.get("value") or "").strip()[:VALUE_MAX]
        uom = str(item.get("uom") or "").strip()[:24]
        if not label or not value:
            continue
        if _set_attribute(working, label, value, uom, category_id, mpn):
            _remember_override(mpn, label, value, uom)
            bundle.set(
                Evidence(
                    field=label,
                    value=value,
                    uom=uom,
                    source_url="reviewer",
                    extractor="reviewer",
                    confidence=0.99,
                )
            )
            messages.append(f"Saved {label}.")
        else:
            messages.append(f"Could not use that {label} value.")

    cleanse_output_row(working, category_id)
    apply_saved_overrides(working, mpn)
    evidence_count = len(bundle.items) if bundle.items else int((preview or {}).get("evidence_count") or 0)
    issues = validate_row(working, category_id=category_id)
    confidence = overall_confidence(working, 0.7, evidence_count)
    from pipeline import _field_sources_from_bundle

    if bundle.mfr_url or bundle.items:
        sources = _field_sources_from_bundle(merge_bundles(EvidenceBundle(), bundle), working)
    else:
        sources = dict((preview or {}).get("field_sources") or {})
        for spec in (preview or {}).get("specs") or []:
            if isinstance(spec, dict) and spec.get("source"):
                sources[str(spec.get("label") or "")] = spec["source"]
        for flag in flags or []:
            if isinstance(flag, dict) and flag.get("label"):
                sources.pop(str(flag["label"]), None)
        for item in attributes or []:
            if isinstance(item, dict) and item.get("label"):
                sources[str(item["label"])] = "reviewer"
    return {
        "row": working,
        "category_id": category_id,
        "confidence_band": confidence,
        "evidence_count": evidence_count,
        "issues": issues,
        "field_sources": sources,
        "messages": messages,
    }
