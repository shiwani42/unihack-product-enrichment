#!/usr/bin/env python3
"""Validate PNG screenshot size and dimensions using only the standard library."""

import argparse
import struct
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--min-bytes", type=int, default=80_000)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    return parser.parse_args()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        header = source.read(24)
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise ValueError("not a valid PNG")
    return struct.unpack(">II", header[16:24])


def main() -> None:
    args = parse_args()
    failures: list[str] = []
    for path in args.paths:
        try:
            size = path.stat().st_size
            width, height = png_dimensions(path)
            if size < args.min_bytes:
                failures.append(f"{path}: only {size:,} bytes")
            if (width, height) != (args.width, args.height):
                failures.append(
                    f"{path}: {width}x{height}, expected {args.width}x{args.height}"
                )
            print(f"{path}: {width}x{height}, {size:,} bytes")
        except (OSError, ValueError) as error:
            failures.append(f"{path}: {error}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
