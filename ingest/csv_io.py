import csv
from pathlib import Path

from app.config import DEFAULT_OUTPUT_HEADERS


def load_output_headers(path: Path | None = None) -> list[str]:
    header_path = path or DEFAULT_OUTPUT_HEADERS
    with header_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return next(reader)


def read_input_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_output_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def empty_output_row(headers: list[str]) -> dict[str, str]:
    return {header: "" for header in headers}
