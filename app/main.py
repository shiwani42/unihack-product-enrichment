import json
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.config import DEFAULT_INPUT, DEFAULT_OUTPUT_HEADERS, REFERENCE_MPNS, OUTPUT_DIR, TAXONOMY_PATH
from app.ui_sections import row_preview
from ingest.csv_io import load_output_headers, read_input_rows, write_output_rows
from ingest.export_io import write_output_xlsx, write_provenance_json
from pipeline import enrich_input_row
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
        "Mfg_Part_Num": "49-94-3000",
        "Part_Desc": '3" x 0.040" x 3/8" Metal Cut Off Wheel 20000 RPM',
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
        "Mfg_Part_Num": "23-615-180",
        "Part_Desc": '6" 6-Hole Grip Sanding Disc 180 Grit Aluminum Oxide',
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


def _filter_rows(rows: list[dict[str, str]], filter_name: str) -> list[dict[str, str]]:
    if filter_name == "dishwasher":
        return [row for row in rows if "dishwasher" in row["Part_Desc"].lower()]
    if filter_name == "appde":
        return [row for row in rows if "APPDE" in row.get("Part_Manuf", "")]
    return rows


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


def _stream_enrichment(rows: list[dict[str, str]], filter_name: str | None):
    headers = load_output_headers()
    reports = []
    enriched_rows = []
    previews = []
    total = len(rows)

    yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

    for index, row in enumerate(rows, start=1):
        mpn = row["Mfg_Part_Num"]
        brand_hint = row.get("DIB_Brand") or row.get("E1_Brand") or row.get("Part_Manuf") or "distributor input"
        msg = f"Processing {mpn} ({brand_hint})"
        yield f"data: {json.dumps({'type': 'step', 'phase': 'resolve', 'current': index, 'total': total, 'mpn': mpn, 'brand_hint': brand_hint, 'message': msg})}\n\n"

        result = enrich_input_row(row, headers)
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

        yield f"data: {json.dumps({'type': 'row', 'current': index, 'total': total, 'mpn': mpn, 'brand': result.row.get('BRAND_NAME', ''), 'category': result.row.get('Fine', result.category_id), 'filled': preview['filled_fields'], 'confidence': result.confidence_band, 'preview': preview})}\n\n"

    summary = summarize_reports(reports) if reports else {}
    payload = {"summary": summary, "rows": reports_to_dicts(reports), "previews": previews}
    _save_last_run(payload, filter_name=filter_name, enriched_rows=enriched_rows)

    yield f"data: {json.dumps({'type': 'complete', 'rows': len(enriched_rows), 'filter': filter_name, 'summary': summary, 'previews': previews})}\n\n"


@app.get("/api/enrich/stream")
def enrich_stream(limit: int = 10, filter: str = "dishwasher") -> StreamingResponse:
    rows = read_input_rows(DEFAULT_INPUT)
    rows = _filter_rows(rows, filter)
    if limit > 0:
        rows = rows[:limit]
    return StreamingResponse(
        _stream_enrichment(rows, filter_name=filter),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/enrich/sample")
async def enrich_sample(
    limit: int = Form(10),
    filter: str = Form("dishwasher"),
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temp_input = OUTPUT_DIR / "upload_input.csv"
    temp_input.write_bytes(await file.read())
    rows = read_input_rows(temp_input)
    if limit > 0:
        rows = rows[:limit]
    enriched, report = await run_in_threadpool(_enrich_rows, rows)
    _save_last_run(report, enriched_rows=enriched)
    return {
        "rows": len(enriched),
        "output_path": str(OUTPUT_DIR / "upload_output.csv"),
        **report,
    }


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

