#!/usr/bin/env python3
"""CLI wrapper: PYTHONPATH=. python3 scripts/harvest_brands.py --dry-run"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sources.brand_harvest import build_harvest_parser  # noqa: E402


def main() -> None:
    parser = build_harvest_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
