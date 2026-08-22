import csv
import io
from pathlib import Path

from app.config import DEFAULT_OUTPUT_HEADERS


def load_output_headers(path: Path | None = None) -> list[str]:
    header_path = path or DEFAULT_OUTPUT_HEADERS
    with header_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return next(reader)


def read_input_rows(path: Path, max_rows: int | None = None) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return _normalize_input_rows(csv.DictReader(handle), max_rows=max_rows)


def read_input_rows_from_text(text: str, max_rows: int | None = None) -> list[dict[str, str]]:
    handle = io.StringIO(text or "")
    return _normalize_input_rows(csv.DictReader(handle), max_rows=max_rows)


def _normalize_input_rows(reader: csv.DictReader, max_rows: int | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {str(key).strip(): ("" if value is None else str(value).strip()) for key, value in raw.items() if key}
        if any(row.values()):
            rows.append(row)
            if max_rows is not None and len(rows) >= max_rows:
                break
    return rows


def write_output_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def existing_output_mpns(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return {row.get("Mfg_Part_Num", "") for row in csv.DictReader(handle) if row.get("Mfg_Part_Num")}


def append_output_row(path: Path, headers: list[str], row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow({header: row.get(header, "") for header in headers})


def empty_output_row(headers: list[str]) -> dict[str, str]:
    return {header: "" for header in headers}
