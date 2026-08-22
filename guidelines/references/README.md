# Reference files drop zone

The organizer reference files are downloadable only from the hackathon
dashboard (Resources section) - they require your login and cannot be
fetched by scripts.

Drop them into this folder with their original names, then run:

    PYTHONPATH=. python3 scripts/import_references.py

| File | Activates |
|------|-----------|
| `Unicat_Lov_v1_0_Updated_With_Remarks.xlsx` | Real LOV validation + compliance LOV-rate metric (`data/reference/lov_values.json`) |
| `Unilog_Master_UOM_Standards_Abbreviations_and_Terms.xlsx` | Approved UOM abbreviation checks in compliance report |
| `UniCat_Manufacturer_and_Brand_List.xlsx` | Exact legal brand casing (® / ™) via identity canonicalization |
| `Decimal_Fraction.xlsx` | Decimal->fraction lookup table |
| `Unilog-Sample_200_Items-Input-vs-Output.xlsx` | 200-row ground-truth scorer: `PYTHONPATH=. python3 scripts/score_ground_truth.py` |

Nothing here is required for the pipeline to run - it degrades gracefully.
