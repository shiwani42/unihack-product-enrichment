import csv
import io
import os
import re
import threading
from collections import Counter, defaultdict, deque
from pathlib import Path

from app.config import DEFAULT_OUTPUT_HEADERS

_ILLEGAL_CELL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PDF_MAGIC = "%PDF"
_append_lock = threading.Lock()


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


def is_readable_text(value: str) -> bool:
    """False for PDF bytes, C0 controls, or mostly non-printable scrap."""
    text = "" if value is None else str(value)
    if not text:
        return True
    if text.lstrip().startswith(_PDF_MAGIC):
        return False
    if _ILLEGAL_CELL.search(text):
        return False
    sample = text[:4000]
    printable = sum(1 for ch in sample if ch.isprintable() or ch in "\n\t\r")
    return printable / max(len(sample), 1) >= 0.85


def sanitize_cell(value: str) -> str:
    """Drop cells that cannot be written to CSV/Excel (binary PDF leftovers, C0 controls)."""
    text = "" if value is None else str(value)
    if not is_readable_text(text):
        return ""
    return text


def _clean_row(headers: list[str], row: dict[str, str]) -> dict[str, str]:
    return {header: sanitize_cell(row.get(header, "")) for header in headers}


def write_output_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(_clean_row(headers, row))


def existing_output_mpns(path: Path) -> set[str]:
    return set(output_mpn_counts(path))


def output_mpn_counts(path: Path) -> Counter:
    counts: Counter[str] = Counter()
    if not path.exists() or path.stat().st_size == 0:
        return counts
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mpn = (row.get("Mfg_Part_Num") or "").strip()
            if mpn:
                counts[mpn] += 1
    return counts


def pending_input_rows(input_rows: list[dict[str, str]], output_path: Path) -> list[dict[str, str]]:
    """Input rows not yet checkpointed. Duplicate MPNs are counted, not treated as one skip."""
    done = output_mpn_counts(output_path)
    seen: Counter[str] = Counter()
    pending: list[dict[str, str]] = []
    for row in input_rows:
        mpn = (row.get("Mfg_Part_Num") or "").strip()
        seen[mpn] += 1
        if seen[mpn] > done[mpn]:
            pending.append(row)
    return pending


def order_output_like_input(
    input_rows: list[dict[str, str]],
    output_rows: list[dict[str, str]],
    headers: list[str],
) -> list[dict[str, str]]:
    buckets: dict[str, deque] = defaultdict(deque)
    for row in output_rows:
        buckets[(row.get("Mfg_Part_Num") or "").strip()].append(row)
    ordered: list[dict[str, str]] = []
    for inp in input_rows:
        mpn = (inp.get("Mfg_Part_Num") or "").strip()
        if buckets[mpn]:
            ordered.append(buckets[mpn].popleft())
        else:
            filled = {header: "" for header in headers}
            filled.update({key: inp.get(key, "") for key in inp})
            ordered.append(filled)
    return ordered


def append_output_row(path: Path, headers: list[str], row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _clean_row(headers, row)
    with _append_lock:
        new_file = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(payload)
            handle.flush()
            os.fsync(handle.fileno())


def empty_output_row(headers: list[str]) -> dict[str, str]:
    return {header: "" for header in headers}
