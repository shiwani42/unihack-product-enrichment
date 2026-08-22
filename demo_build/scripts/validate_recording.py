#!/usr/bin/env python3
"""Validate an exact-frame CFR walkthrough using ffprobe."""

import argparse
import json
import subprocess
from fractions import Fraction
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", default="30")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--codec", default="h264")
    parser.add_argument("--pixel-format", default="yuv420p")
    parser.add_argument("--min-bytes", type=int, default=300_000)
    parser.add_argument("--duration-tolerance-frames", type=float, default=1.0)
    return parser.parse_args()


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"ffprobe exited {result.returncode}")
    return json.loads(result.stdout)


def main() -> None:
    args = parse_args()
    try:
        expected_rate = Fraction(args.fps)
    except (ValueError, ZeroDivisionError) as error:
        raise SystemExit(f"invalid --fps {args.fps!r}: {error}") from error
    if expected_rate <= 0 or args.duration <= 0:
        raise SystemExit("fps and duration must be positive")
    if args.width <= 0 or args.height <= 0 or args.min_bytes < 0:
        raise SystemExit("dimensions must be positive and min-bytes cannot be negative")
    if args.duration_tolerance_frames < 0:
        raise SystemExit("duration-tolerance-frames cannot be negative")
    expected_frames = round(float(expected_rate) * args.duration)
    failures: list[str] = []

    try:
        metadata = probe(args.path)
        stream = metadata["streams"][0]
        duration = float(metadata["format"]["duration"])
        size = int(metadata["format"]["size"])
        frames = int(stream["nb_read_frames"])
        nominal_rate = Fraction(stream["r_frame_rate"])
        average_rate = Fraction(stream["avg_frame_rate"])

        if stream["codec_name"] != args.codec:
            failures.append(f"codec {stream['codec_name']} != {args.codec}")
        if stream["pix_fmt"] != args.pixel_format:
            failures.append(f"pixel format {stream['pix_fmt']} != {args.pixel_format}")
        if (stream["width"], stream["height"]) != (args.width, args.height):
            failures.append(
                f"dimensions {stream['width']}x{stream['height']} != "
                f"{args.width}x{args.height}"
            )
        if nominal_rate != expected_rate or average_rate != expected_rate:
            failures.append(
                f"frame rate nominal={nominal_rate} average={average_rate} "
                f"expected={expected_rate}"
            )
        if frames != expected_frames:
            failures.append(f"frames {frames} != {expected_frames}")
        tolerance = args.duration_tolerance_frames / float(expected_rate)
        if abs(duration - args.duration) > tolerance:
            failures.append(
                f"duration {duration:.6f}s outside {args.duration:.6f}s "
                f"+/- {tolerance:.6f}s"
            )
        if size < args.min_bytes:
            failures.append(f"size {size:,} bytes < {args.min_bytes:,}")
    except (FileNotFoundError, IndexError, KeyError, ValueError) as error:
        failures.append(str(error))

    if failures:
        raise SystemExit("\n".join(f"{args.path}: {failure}" for failure in failures))

    print(
        f"{args.path}: {stream['codec_name']} {stream['pix_fmt']} "
        f"{stream['width']}x{stream['height']} {average_rate}fps, "
        f"{frames} frames, {duration:.3f}s, {size:,} bytes"
    )


if __name__ == "__main__":
    main()
