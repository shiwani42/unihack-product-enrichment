import json
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS, REFERENCE_MPNS, OUTPUT_DIR, TAXONOMY_PATH
from app.ui_sections import row_preview
from ingest.csv_io import load_output_headers, read_input_rows, read_input_rows_from_text, write_output_rows, empty_output_row
from ingest.export_io import write_output_xlsx, write_provenance_json
from classify.category_router import route_category
from identity.brand_resolver import resolve_identity
from pipeline import EnrichmentResult, enrich_input_row
from sources.url_store import activate, begin_request, persist_shared, snapshot
from validate.reference_test import compare_rows
from validate.report import build_row_report, reports_to_dicts, summarize_reports

app = FastAPI(title="ProductIntel | AI Catalog Enrichment", version="0.2.0")

STATIC_DIR = Path(__file__).resolve().parent / "static"
LAST_REPORT_PATH = OUTPUT_DIR / "last_report.json"
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "classify" / "templates"

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

_SEED_FILES = ("batch_enriched.csv", "batch_enriched.xlsx", "enriched.xlsx",
               "field_provenance.json", "last_report.json")


def _seed_output_dir() -> None:
    """Serverless cold start: /tmp is empty, so copy bundled delivery artifacts."""
    if OUTPUT_DIR == Path(__file__).resolve().parents[1] / "output":
        return
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for name in _SEED_FILES:
            src = Path(__file__).resolve().parents[1] / "output" / name
            dst = OUTPUT_DIR / name
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
    except Exception:
        pass


_seed_output_dir()
activate()
from scripts.import_references import ensure_official_references

ensure_official_references()

UPLOAD_ROW_CAP = 2000
INPUT_COLUMNS = ("Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf")


def _coerce_input_row(raw: dict) -> dict[str, str]:
    return {key: str((raw or {}).get(key, "") or "") for key in INPUT_COLUMNS}


def _sse_response(iterator) -> StreamingResponse:
    return StreamingResponse(
        iterator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


PRESETS = [
    {
        "id": "frigidaire_dishwasher",
        "name": "Frigidaire Dishwasher",
        "badge": "Appliances",
        "Mfg_Part_Num": "PDSH4816AF",
        "Part_Desc": "Built-In Dishwasher 24 in 49 dBA 120 V 15 A Leg",
        "E1_Brand": "DIB",
        "Unilog_Brand": "FRIGIDAIRE",
        "DIB_Brand": "FRIGIDAIRE GALLERY",
        "Part_Manuf": "APPDE",
    },
    {
        "id": "whirlpool_dishwasher",
        "name": "Whirlpool Eco Dishwasher",
        "badge": "Appliances",
        "Mfg_Part_Num": "WDTS7024RZ",
        "Part_Desc": "Eco Series Built-in Dishwasher 41 dBA 120V 10A SST",
        "E1_Brand": "APPDE",
        "Unilog_Brand": "WHIRLPOOL",
        "DIB_Brand": "WHIRLPOOL",
        "Part_Manuf": "Whirlpool Corporation",
    },
    {
        "id": "milwaukee_cutoff",
        "name": "Milwaukee Cut-Off Wheel",
        "badge": "Abrasives",
        "Mfg_Part_Num": "49-94-0013",
        "Part_Desc": '49-94-0013 Milw 5"x.045"x7/8" Metal Cut Off Disc',
        "E1_Brand": "MILWAUKEE",
        "Unilog_Brand": "",
        "DIB_Brand": "MILWAUKEE",
        "Part_Manuf": "Milwaukee Electric Tool",
    },
    {
        "id": "hunter_fan",
        "name": "Hunter Ceiling Fan",
        "badge": "Fans",
        "Mfg_Part_Num": "59243",
        "Part_Desc": 'Dempsey 44" Low Profile Fresh White Ceiling Fan with LED Light',
        "E1_Brand": "HUNTER",
        "Unilog_Brand": "",
        "DIB_Brand": "",
        "Part_Manuf": "Hunter Fan Company",
    },
    {
        "id": "ge_range",
        "name": "GE Freestanding Electric Range",
        "badge": "Appliances",
        "Mfg_Part_Num": "JB645RKSS",
        "Part_Desc": '30" Free-Standing Electric Range Stainless Steel 5.3 Cu. Ft.',
        "E1_Brand": "APPDE",
        "Unilog_Brand": "GE APPLIANCES",
        "DIB_Brand": "GE",
        "Part_Manuf": "GE Appliances",
    },
    {
        "id": "mirka_abrasive",
        "name": "Mirka Sanding Disc",
        "badge": "Abrasives",
        "Mfg_Part_Num": "5B-332-080",
        "Part_Desc": '5B-332-080 HIOLIT 5" P80',
        "E1_Brand": "",
        "Unilog_Brand": "",
        "DIB_Brand": "MIRKA",
        "Part_Manuf": "Mirka Abrasives",
    },
    {
        "id": "kichler_led",
        "name": "Kichler LED Downlight",
        "badge": "Lighting",
        "Mfg_Part_Num": "43846WHLED30",
        "Part_Desc": 'Direct-to-Ceiling 6" Round LED Downlight 3000K 120V White',
        "E1_Brand": "KICHLER",
        "Unilog_Brand": "",
        "DIB_Brand": "",
        "Part_Manuf": "Kichler Lighting",
    },
    {
        "id": "generic_pipe",
        "name": "Industrial Brass Pipe Fitting",
        "badge": "Industrial",
        "Mfg_Part_Num": "PF-BR-050",
        "Part_Desc": '1/2" NPT Female x 1/2" NPT Male Brass Hex Bushing Fitting 150 PSI',
        "E1_Brand": "",
        "Unilog_Brand": "",
        "DIB_Brand": "",
        "Part_Manuf": "Industrial Hardware",
    },
]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0"}


SEGMENT_ALIASES = {
    "dishwasher": "built_in_dishwasher",
}


def _row_category_id(row: dict[str, str]) -> str:
    identity = resolve_identity(
        row.get("Mfg_Part_Num", ""),
        row.get("Part_Desc", ""),
        row.get("E1_Brand", ""),
        row.get("DIB_Brand", ""),
        row.get("Part_Manuf", ""),
        row.get("Unilog_Brand", ""),
    )
    return route_category(row.get("Part_Desc", ""), identity.brand_key).category_id


def _filter_rows(rows: list[dict[str, str]], filter_name: str) -> list[dict[str, str]]:
    if not filter_name:
        return rows
    if filter_name == "appde":
        return [row for row in rows if "APPDE" in row.get("Part_Manuf", "")]
    category_id = SEGMENT_ALIASES.get(filter_name, filter_name)
    return [row for row in rows if _row_category_id(row) == category_id]


def _enrich_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict]:
    headers = load_output_headers()
    reports = []
    enriched_rows = []
    previews = []
    for row in rows:
        result = enrich_input_row(row, headers)
        enriched_rows.append(result.row)
        report = build_row_report(
            mpn=row["Mfg_Part_Num"],
            row=result.row,
            confidence_band=result.confidence_band,
            evidence_count=result.evidence_count,
            issues=result.issues,
            field_sources=result.field_sources,
            category_id=result.category_id,
        )
        reports.append(report)
        report_dict = reports_to_dicts([report])[0]
        previews.append(row_preview(result.row, report_dict, input_row=row))

    summary = summarize_reports(reports) if reports else {}
    payload = {"summary": summary, "rows": reports_to_dicts(reports), "previews": previews}
    return enriched_rows, payload


def _save_last_run(payload: dict, filter_name: str | None = None, enriched_rows: list[dict[str, str]] | None = None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LAST_REPORT_PATH.write_text(
        json.dumps({"filter": filter_name, **payload}, indent=2),
        encoding="utf-8",
    )
    if enriched_rows:
        headers = load_output_headers()
        write_output_rows(OUTPUT_DIR / "upload_output.csv", headers, enriched_rows)
        try:
            write_output_xlsx(OUTPUT_DIR / "enriched.xlsx", headers, enriched_rows)
        except Exception:
            pass
        try:
            rows_data = payload.get("rows", [])
            write_provenance_json(
                OUTPUT_DIR / "field_provenance.json",
                [
                    {
                        "mpn": r.get("mpn", ""),
                        "category_id": r.get("category_id", ""),
                        "field_sources": r.get("field_sources", {}),
                        "issues": r.get("issues", []),
                    }
                    for r in rows_data
                ],
            )
        except Exception:
            pass


@app.get("/api/presets")
def get_presets() -> list[dict]:
    return PRESETS


@app.get("/api/reference")
def reference_scores() -> dict:
    headers = load_output_headers()
    reference_rows = read_input_rows(DEFAULT_OUTPUT_HEADERS)
    reference_by_mpn = {row["Mfg_Part_Num"]: row for row in reference_rows if row.get("Mfg_Part_Num")}
    input_rows = read_input_rows(DEFAULT_INPUT)
    input_by_mpn = {row["Mfg_Part_Num"]: row for row in input_rows}

    results = []
    for mpn in REFERENCE_MPNS:
        expected = reference_by_mpn.get(mpn)
        source = input_by_mpn.get(mpn)
        if not expected or not source:
            continue
        actual = enrich_input_row(source, headers).row
        score = compare_rows(expected, actual, mpn)
        results.append(
            {
                "mpn": mpn,
                "score": round(score.score, 4),
                "score_pct": round(score.score * 100, 1),
                "matches": score.matches,
                "expected_filled": score.expected_filled,
                "missing_count": len(score.missing),
                "mismatch_count": len(score.mismatches),
                "brand": actual.get("BRAND_NAME", ""),
                "category": actual.get("Fine", "Built-In Dishwasher"),
            }
        )
    avg = round(sum(item["score"] for item in results) / len(results), 4) if results else 0
    return {"benchmarks": results, "average_score": avg, "average_pct": round(avg * 100, 1)}


@app.get("/api/taxonomy")
def get_taxonomy() -> dict:
    leaves = []
    if TAXONOMY_PATH.exists():
        try:
            leaves = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    templates = []
    if TEMPLATES_DIR.exists():
        for template_file in sorted(TEMPLATES_DIR.glob("*.json")):
            try:
                data = json.loads(template_file.read_text(encoding="utf-8"))
                templates.append({
                    "category_id": data.get("category_id", template_file.stem),
                    "product_name": data.get("product_name", ""),
                    "classpath": data.get("classpath", ""),
                    "dept": data.get("dept", ""),
                    "class": data.get("class", ""),
                    "fine": data.get("fine", ""),
                    "attribute_count": len(data.get("attribute_labels", [])),
                    "attribute_labels": data.get("attribute_labels", []),
                })
            except Exception:
                pass

    return {
        "leaf_count": len(leaves),
        "leaves": leaves,
        "template_count": len(templates),
        "templates": templates,
    }


@app.get("/api/last-run")
def last_run() -> dict:
    if not LAST_REPORT_PATH.exists():
        return {"summary": {"rows": 0}, "rows": [], "previews": []}
    return json.loads(LAST_REPORT_PATH.read_text(encoding="utf-8"))


def _output_csv_path() -> Path:
    return OUTPUT_DIR / "upload_output.csv"


def _load_output_row(mpn: str, headers: list[str]) -> dict[str, str] | None:
    path = _output_csv_path()
    if not path.exists():
        return None
    for row in read_input_rows(path):
        if (row.get("Mfg_Part_Num") or "").strip() == mpn:
            filled = {header: "" for header in headers}
            filled.update(row)
            return filled
    return None


def _preview_from_last_run(mpn: str) -> dict | None:
    if not LAST_REPORT_PATH.exists():
        return None
    try:
        payload = json.loads(LAST_REPORT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for preview in payload.get("previews") or []:
        if isinstance(preview, dict) and preview.get("mpn") == mpn:
            return preview
    return None


def _upsert_catalog_row(mpn: str, row: dict[str, str], preview: dict, report_dict: dict) -> None:
    headers = load_output_headers()
    path = _output_csv_path()
    existing = read_input_rows(path) if path.exists() else []
    replaced = False
    merged_rows: list[dict[str, str]] = []
    for item in existing:
        if (item.get("Mfg_Part_Num") or "").strip() == mpn and not replaced:
            merged_rows.append(row)
            replaced = True
        else:
            merged_rows.append(item)
    if not replaced:
        merged_rows.append(row)
    payload = last_run()
    previews = [item for item in (payload.get("previews") or []) if isinstance(item, dict)]
    reports = [item for item in (payload.get("rows") or []) if isinstance(item, dict)]
    previews = [item for item in previews if item.get("mpn") != mpn] + [preview]
    reports = [item for item in reports if item.get("mpn") != mpn] + [report_dict]
    payload["previews"] = previews
    payload["rows"] = reports
    payload["summary"] = payload.get("summary") or {}
    payload["summary"]["rows"] = len(previews)
    _save_last_run(payload, filter_name=payload.get("filter"), enriched_rows=merged_rows)


@app.post("/api/catalog/contribute")
async def catalog_contribute(request: Request) -> dict:
    """Inspect-drawer hint: a known product URL, typed specs, or a flagged value."""
    from identity.brand_resolver import resolve_identity
    from sources.reviewer import contribute
    from sources.url_store import persist_shared, snapshot
    from validate.rules import ValidationIssue

    body = await request.json()
    mpn = str(body.get("mpn") or "").strip()
    if not mpn:
        return JSONResponse({"error": "mpn required"}, status_code=400)
    memory = body.get("url_memory") if isinstance(body.get("url_memory"), dict) else None
    begin_request(memory)
    headers = load_output_headers()
    preview = body.get("preview") if isinstance(body.get("preview"), dict) else _preview_from_last_run(mpn)
    input_row = {}
    if isinstance(body.get("input"), dict):
        input_row = {key: str(body["input"].get(key) or "") for key in INPUT_COLUMNS}
    elif preview:
        input_row = {key: str((preview.get("input") or {}).get(key) or "") for key in INPUT_COLUMNS}
    input_row["Mfg_Part_Num"] = mpn
    identity = resolve_identity(
        mpn=mpn,
        part_desc=input_row.get("Part_Desc", ""),
        e1_brand=input_row.get("E1_Brand", ""),
        dib_brand=input_row.get("DIB_Brand", ""),
        part_manuf=input_row.get("Part_Manuf", ""),
        unilog_brand=input_row.get("Unilog_Brand", ""),
    )
    names = [identity.manufacturer_name, identity.brand_name, identity.brand_key]
    result = await run_in_threadpool(
        lambda: contribute(
            mpn=mpn,
            preview=preview,
            row=_load_output_row(mpn, headers),
            headers=headers,
            url=str(body.get("url") or ""),
            attributes=body.get("attributes") if isinstance(body.get("attributes"), list) else [],
            flags=body.get("flags") if isinstance(body.get("flags"), list) else [],
            names=[name for name in names if name],
            domains=list(identity.domains or []),
            category_id=str(body.get("category_id") or (preview or {}).get("category_id") or ""),
        )
    )
    issues = result.get("issues") or []
    report = build_row_report(
        mpn=mpn,
        row=result["row"],
        confidence_band=result.get("confidence_band") or "review",
        evidence_count=int(result.get("evidence_count") or 0),
        issues=issues if issues and isinstance(issues[0], ValidationIssue) else issues,
        field_sources=result.get("field_sources") or {},
        category_id=result.get("category_id") or "",
    )
    report_dict = reports_to_dicts([report])[0]
    preview_out = row_preview(result["row"], report_dict, input_row=input_row or result["row"])
    _upsert_catalog_row(mpn, result["row"], preview_out, report_dict)
    url_memory = persist_shared(snapshot())
    return {
        "mpn": mpn,
        "preview": preview_out,
        "messages": result.get("messages") or [],
        "url_memory": url_memory,
    }


@app.post("/api/enrich/single")
async def enrich_single(request: Request) -> dict:
    headers = load_output_headers()
    input_row = {}
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        input_row = await request.json()
    else:
        form = await request.form()
        input_row = {k: str(v) for k, v in form.items()}

    mpn = input_row.get("Mfg_Part_Num", "").strip() or "SAMPLE-SKU"
    input_row["Mfg_Part_Num"] = mpn
    input_row.setdefault("Part_Desc", "")
    input_row.setdefault("E1_Brand", "")
    input_row.setdefault("Unilog_Brand", "")
    input_row.setdefault("DIB_Brand", "")
    input_row.setdefault("Part_Manuf", "")

    result = await run_in_threadpool(enrich_input_row, input_row, headers)
    report = build_row_report(
        mpn=mpn,
        row=result.row,
        confidence_band=result.confidence_band,
        evidence_count=result.evidence_count,
        issues=result.issues,
        field_sources=result.field_sources,
        category_id=result.category_id,
    )
    report_dict = reports_to_dicts([report])[0]
    preview = row_preview(result.row, report_dict, input_row=input_row)

    return {
        "mpn": mpn,
        "category_id": result.category_id,
        "confidence_band": result.confidence_band,
        "evidence_count": result.evidence_count,
        "issues": [f"{i.field}: {i.message}" for i in result.issues],
        "preview": preview,
        "report": report_dict,
    }


def _stream_enrichment(
    rows: list[dict[str, str]],
    filter_name: str | None,
    *,
    abs_offset: int = 0,
    selected_total: int | None = None,
    save: bool = True,
    url_memory: dict | None = None,
):
    headers = load_output_headers()
    reports = []
    enriched_rows = []
    previews = []
    total = selected_total if selected_total is not None else len(rows)
    begin_request(url_memory)

    yield f"data: {json.dumps({'type': 'start', 'total': total, 'offset': abs_offset, 'headers': headers})}\n\n"

    for index, row in enumerate(rows, start=1):
        mpn = row["Mfg_Part_Num"]
        brand_hint = row.get("DIB_Brand") or row.get("E1_Brand") or row.get("Part_Manuf") or "distributor input"
        current = abs_offset + index
        msg = f"Processing {mpn} ({brand_hint})"
        yield f"data: {json.dumps({'type': 'step', 'phase': 'resolve', 'current': current, 'total': total, 'mpn': mpn, 'brand_hint': brand_hint, 'message': msg})}\n\n"

        try:
            result = enrich_input_row(row, headers)
        except Exception as exc:
            output = empty_output_row(headers)
            output["Mfg_Part_Num"] = mpn
            output["MANUFACTURER_PART_NUMBER"] = mpn
            result = EnrichmentResult(
                row=output,
                confidence_band="review",
                evidence_count=0,
                issues=[],
                field_sources={},
                category_id="error",
                error=str(exc),
            )
        enriched_rows.append(result.row)
        report = build_row_report(
            mpn=mpn,
            row=result.row,
            confidence_band=result.confidence_band,
            evidence_count=result.evidence_count,
            issues=result.issues,
            field_sources=result.field_sources,
            category_id=result.category_id,
        )
        reports.append(report)
        report_dict = reports_to_dicts([report])[0]
        preview = row_preview(result.row, report_dict, input_row=row)
        previews.append(preview)

        yield f"data: {json.dumps({'type': 'row', 'current': current, 'total': total, 'mpn': mpn, 'brand': result.row.get('BRAND_NAME', ''), 'category': result.row.get('Fine', result.category_id), 'filled': preview['filled_fields'], 'confidence': result.confidence_band, 'preview': preview})}\n\n"

    summary = summarize_reports(reports) if reports else {}
    payload = {"summary": summary, "rows": reports_to_dicts(reports), "previews": previews}
    if save:
        _save_last_run(payload, filter_name=filter_name, enriched_rows=enriched_rows)

    memory = persist_shared(snapshot())
    yield f"data: {json.dumps({'type': 'complete', 'rows': len(enriched_rows), 'filter': filter_name, 'summary': summary, 'previews': previews, 'reports': reports_to_dicts(reports), 'delivery': enriched_rows, 'offset': abs_offset, 'done': abs_offset + len(rows) >= total, 'url_memory': memory})}\n\n"


@app.get("/api/enrich/stream")
def enrich_stream(
    limit: int = 10,
    filter: str = "",
    offset: int = 0,
    window: int = 0,
    save: int = 1,
) -> StreamingResponse:
    """Enrich a slice of rows. `window` splits a batch across requests so each
    Vercel invocation stays under maxDuration; the client commits at the end.
    """
    rows = read_input_rows(DEFAULT_INPUT)
    rows = _filter_rows(rows, filter)
    if limit > 0:
        rows = rows[:limit]
    total = len(rows)
    start = max(offset, 0)
    slice_rows = rows[start : start + window] if window > 0 else rows[start:]
    return _sse_response(
        _stream_enrichment(
            slice_rows,
            filter_name=filter,
            abs_offset=start,
            selected_total=total,
            save=bool(save),
        )
    )


@app.post("/api/enrich/parse")
async def enrich_parse(
    file: UploadFile = File(...),
    limit: int = Form(0),
) -> dict:
    """Parse an uploaded catalog CSV. Does not enrich — the client windows rows."""
    payload = await file.read()
    text = payload.decode("utf-8-sig", errors="replace")
    parsed = read_input_rows_from_text(text, max_rows=UPLOAD_ROW_CAP + 1)
    truncated = len(parsed) > UPLOAD_ROW_CAP
    rows = [_coerce_input_row(row) for row in parsed[:UPLOAD_ROW_CAP]]
    if limit > 0:
        rows = rows[:limit]
    return {
        "total": len(rows),
        "truncated": truncated,
        "cap": UPLOAD_ROW_CAP,
        "filename": file.filename or "upload.csv",
        "rows": rows,
        "headers": load_output_headers(),
    }


@app.post("/api/enrich/window")
async def enrich_window(request: Request) -> StreamingResponse:
    """Enrich a client-held slice. One Vercel invocation, typically one SKU."""
    body = await request.json()
    raw_rows = body.get("rows") or []
    rows = [_coerce_input_row(row) for row in raw_rows if isinstance(row, dict)]
    offset = max(int(body.get("offset") or 0), 0)
    total = int(body.get("total") or (offset + len(rows)))
    return _sse_response(
        _stream_enrichment(
            rows,
            filter_name=body.get("filter") or "upload",
            abs_offset=offset,
            selected_total=max(total, offset + len(rows)),
            save=False,
            url_memory=body.get("url_memory") if isinstance(body.get("url_memory"), dict) else None,
        )
    )


@app.post("/api/enrich/stream")
async def enrich_stream_post(request: Request) -> StreamingResponse:
    """Same as GET /api/enrich/stream, with session URL memory for Vercel."""
    body = await request.json()
    limit = int(body.get("limit") or 10)
    filter_name = str(body.get("filter") or "")
    offset = max(int(body.get("offset") or 0), 0)
    window = int(body.get("window") or 0)
    save = int(body.get("save") or 0)
    rows = read_input_rows(DEFAULT_INPUT)
    rows = _filter_rows(rows, filter_name)
    if limit > 0:
        rows = rows[:limit]
    total = len(rows)
    slice_rows = rows[offset : offset + window] if window > 0 else rows[offset:]
    return _sse_response(
        _stream_enrichment(
            slice_rows,
            filter_name=filter_name,
            abs_offset=offset,
            selected_total=total,
            save=bool(save),
            url_memory=body.get("url_memory") if isinstance(body.get("url_memory"), dict) else None,
        )
    )


@app.post("/api/enrich/commit")
async def enrich_commit(request: Request) -> dict:
    body = await request.json()
    delivery = body.get("delivery") or []
    payload = {
        "summary": body.get("summary") or {},
        "rows": body.get("rows") or [],
        "previews": body.get("previews") or [],
    }
    _save_last_run(payload, filter_name=body.get("filter"), enriched_rows=delivery)
    return {"ok": True, "rows": len(delivery)}


@app.post("/enrich/sample")
async def enrich_sample(
    limit: int = Form(10),
    filter: str = Form(""),
) -> dict:
    rows = read_input_rows(DEFAULT_INPUT)
    rows = _filter_rows(rows, filter)
    if limit > 0:
        rows = rows[:limit]
    enriched, report = await run_in_threadpool(_enrich_rows, rows)
    _save_last_run(report, filter_name=filter, enriched_rows=enriched)
    return {
        "rows": len(enriched),
        "filter": filter,
        "output_path": str(OUTPUT_DIR / "upload_output.csv"),
        **report,
    }


@app.post("/enrich")
async def enrich(
    file: UploadFile = File(...),
    limit: int = Form(0),
) -> dict:
    """Parse only. Enrichment happens in /api/enrich/window so large files cannot time out."""
    return await enrich_parse(file=file, limit=limit)


@app.get("/download/latest")
@app.get("/download/csv")
def download_csv() -> FileResponse:
    path = OUTPUT_DIR / "upload_output.csv"
    if not path.exists():
        path = OUTPUT_DIR / "enriched.csv"
    if not path.exists():
        path = OUTPUT_DIR / "batch_enriched.csv"
    if not path.exists():
        headers = load_output_headers()
        rows = read_input_rows(DEFAULT_INPUT)[:10]
        enriched, _ = _enrich_rows(rows)
        write_output_rows(path, headers, enriched)
    return FileResponse(path, filename="unilog_enriched_catalog.csv", media_type="text/csv")


@app.get("/download/xlsx")
def download_xlsx() -> FileResponse:
    path = OUTPUT_DIR / "enriched.xlsx"
    if not path.exists():
        path = OUTPUT_DIR / "batch_enriched.xlsx"
    if not path.exists():
        csv_path = OUTPUT_DIR / "upload_output.csv"
        if not csv_path.exists():
            csv_path = OUTPUT_DIR / "enriched.csv"
        headers = load_output_headers()
        if csv_path.exists():
            rows = read_input_rows(csv_path)
            write_output_xlsx(path, headers, rows)
        else:
            rows = read_input_rows(DEFAULT_INPUT)[:10]
            enriched, _ = _enrich_rows(rows)
            write_output_xlsx(path, headers, enriched)
    return FileResponse(path, filename="unilog_enriched_catalog.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/download/provenance")
def download_provenance() -> FileResponse:
    path = OUTPUT_DIR / "field_provenance.json"
    if not path.exists():
        write_provenance_json(path, [{"status": "no_run_yet"}])
    return FileResponse(path, filename="field_provenance.json", media_type="application/json")

