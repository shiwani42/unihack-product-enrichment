#!/usr/bin/env python3
"""Fetch Inter + JetBrains Mono woff2 files into public/fonts for offline rendering."""

import argparse
import re
import urllib.request
from pathlib import Path

CSS_URLS = [
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap",
    "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap",
]
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BLOCK_RE = re.compile(r"@font-face\s*\{[^}]+\}", re.DOTALL)
URL_RE = re.compile(r"url\((https://[^)]+\.woff2)\)")
FAMILY_RE = re.compile(r"font-family:\s*'([^']+)'")
WEIGHT_RE = re.compile(r"font-weight:\s*(\d+)")
LATIN_MARKER = "U+0000-00FF"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    for css_url in CSS_URLS:
        css = fetch(css_url).decode("utf-8")
        for block in BLOCK_RE.findall(css):
            if LATIN_MARKER not in block:
                continue
            family = FAMILY_RE.search(block)
            weight = WEIGHT_RE.search(block)
            url = URL_RE.search(block)
            if not (family and weight and url):
                continue
            slug = family.group(1).replace(" ", "")
            target = args.output / f"{slug}-{weight.group(1)}.woff2"
            if not target.exists() or target.stat().st_size < 10_000:
                target.write_bytes(fetch(url.group(1)))
            saved.append(target)

    if not saved:
        raise SystemExit("no fonts downloaded")
    for path in saved:
        print(f"font {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
