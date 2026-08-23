# Reference files drop zone

Put **official Solution Guide workbooks** here when testing locally.

Download them from the hackathon dashboard (Resources). Scripts cannot fetch
them for you. Original filenames work; renamed files are classified from
column headers.

```
guidelines/references/     ← drop the .xlsx files here (preferred)
guidelines/                ← also scanned
UNILOG_REFERENCES_DIR      ← optional extra folder
```

Then run enrich as usual (`cli.py batch`, `cli.py enrich`, or the local UI).
Import is automatic. You do not have to run the importer first.

This folder is **not** for the product input CSV. That file is:

- sample: `guidelines/Unihack_ Sample Dataset - Input.csv`
- or `--input path/to/your.csv` / Enrich → drop CSV in the UI

Until workbooks are present, the pipeline uses mined sample standards in
`data/reference/`, then the small built-in JSON files. Official files overlay
those lookups. Nothing here is required for the pipeline to run.

To convert without enriching:

    PYTHONPATH=. python3 scripts/import_references.py

| File | Activates |
|------|-----------|
| `Unicat_Lov_v1_0_Updated_With_Remarks.xlsx` | LOV validation (`data/reference/lov_values.json`) |
| `FAUCETS_LOV.xlsx` / `Fittings_LOV.xlsx` | Merged into the same LOV lookup |
| `Unilog_Master_UOM_Standards_Abbreviations_and_Terms.xlsx` | Approved UOM abbreviations |
| `UniCat_Manufacturer_and_Brand_List.xlsx` | Legal brand casing (® / ™) |
| `Decimal_Fraction.xlsx` | Decimal → fraction table |
| Taxonomy workbook with a Classpath column (not the LOV sheet) | Extra leaf routing |
| `Unilog-Sample_200_Items-Input-vs-Output.xlsx` | `PYTHONPATH=. python3 scripts/score_ground_truth.py` |
