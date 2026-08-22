from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse

from app.config import OUTPUT_DIR
from ingest.csv_io import load_output_headers, read_input_rows, write_output_rows
from pipeline import enrich_input_row

app = FastAPI(title="UniHack Product Enrichment", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/enrich")
async def enrich(file: UploadFile = File(...)) -> dict[str, str]:
    headers = load_output_headers()
    temp_input = OUTPUT_DIR / "upload_input.csv"
    temp_output = OUTPUT_DIR / "upload_output.csv"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temp_input.write_bytes(await file.read())
    rows = read_input_rows(temp_input)
    enriched = [enrich_input_row(row, headers).row for row in rows]
    write_output_rows(temp_output, headers, enriched)
    return {"output_path": str(temp_output), "rows": str(len(enriched))}


@app.get("/download/latest")
def download_latest() -> FileResponse:
    path = OUTPUT_DIR / "upload_output.csv"
    return FileResponse(path, filename="enriched.csv", media_type="text/csv")
