import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "guidelines" / "Unihack_ Expected Output - Delivery Format.csv"
OUTPUT = ROOT / "data" / "crosswalk" / "mpn_to_unilog.json"


def main() -> None:
    import csv

    crosswalk: dict[str, dict[str, str]] = {}
    with REFERENCE.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            mpn = row.get("Mfg_Part_Num", "").strip()
            if not mpn:
                continue
            part_number = row.get("PART_NUMBER", "").strip()
            sku = row.get("SKU - MY_PART_NUMBER", "").strip()
            if part_number or sku:
                crosswalk[mpn.upper()] = {
                    "PART_NUMBER": part_number,
                    "SKU - MY_PART_NUMBER": sku,
                }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(crosswalk, indent=2), encoding="utf-8")
    print(f"Wrote {len(crosswalk)} crosswalk entries to {OUTPUT}")


if __name__ == "__main__":
    main()
