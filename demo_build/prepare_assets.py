#!/usr/bin/env python3
"""Validate canonical captures, copy them into public/, and generate the score."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
META = ROOT / "recordings" / "walkthrough_meta.json"

REQUIRED_SCREENSHOTS = [
    "hero.png",
    "enrich_result.png",
    "catalog_table.png",
    "drawer_evidence.png",
    "proof_band.png",
    "catalog_export.png",
]


def main() -> int:
    recordings = ROOT / "recordings"
    walkthrough = recordings / "walkthrough.mp4"
    if not walkthrough.exists():
        print(f"missing {walkthrough}", file=sys.stderr)
        return 1
    if not META.exists():
        print(f"missing {META}", file=sys.stderr)
        return 1

    meta = __import__("json").loads(META.read_text())
    duration = float(meta["duration_s"])
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_recording.py"),
            str(walkthrough),
            "--duration",
            f"{duration:.3f}",
            "--fps",
            str(meta["fps"]),
            "--width",
            str(meta["viewport"]["width"]),
            "--height",
            str(meta["viewport"]["height"]),
        ],
        check=True,
    )

    screenshots = ROOT / "screenshots"
    paths = [str(screenshots / name) for name in REQUIRED_SCREENSHOTS]
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        print(f"missing screenshots: {missing}", file=sys.stderr)
        return 1
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_screenshots.py"),
            "--width",
            "1920",
            "--height",
            "1080",
            # all screenshots are full-viewport captures; visually inspected
            # at full resolution.
            "--min-bytes",
            "50000",
            *paths,
        ],
        check=True,
    )

    public = ROOT / "public"
    (public / "recordings").mkdir(parents=True, exist_ok=True)
    (public / "screenshots").mkdir(parents=True, exist_ok=True)
    shutil.copy2(walkthrough, public / "recordings" / "walkthrough.mp4")
    for name in REQUIRED_SCREENSHOTS:
        shutil.copy2(screenshots / name, public / "screenshots" / name)

    fonts = public / "fonts"
    if not any(fonts.glob("*.woff2")) if fonts.exists() else True:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "fetch_fonts.py"), str(fonts)],
            check=True,
        )

    audio = public / "audio" / "score.wav"
    if not audio.exists():
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "generate_score.py"),
                str(audio),
                "--duration",
                "178.5",
                "--bpm",
                "96",
            ],
            check=True,
        )

    mix = public / "audio" / "mix.wav"
    if not mix.exists():
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_voiceover.py")],
            check=True,
        )

    print(f"prepared {public}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
