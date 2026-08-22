#!/usr/bin/env python3
"""Mine recurring tokens from Part_Desc to expand abbreviation dictionary."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "guidelines" / "Unihack_ Sample Dataset - Input.csv"
ABBREV = ROOT / "ingest" / "abbreviations.json"
OUTPUT = ROOT / "output" / "mined_abbreviations.json"

TOKEN_RE = re.compile(r"\b([A-Z]{2,5}|[A-Z][a-z]{1,3})\b")


def main() -> None:
    existing = json.loads(ABBREV.read_text(encoding="utf-8")) if ABBREV.exists() else {}
    counts: Counter = Counter()
    with INPUT.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for token in TOKEN_RE.findall(row["Part_Desc"]):
                if token.upper() in existing:
                    continue
                if token.lower() in {"the", "and", "for", "with"}:
                    continue
                counts[token] += 1

    mined = {token: token for token, count in counts.most_common(80) if count >= 3 and len(token) <= 5}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(mined, indent=2), encoding="utf-8")
    print(f"Mined {len(mined)} candidate tokens -> {OUTPUT}")


if __name__ == "__main__":
    main()
