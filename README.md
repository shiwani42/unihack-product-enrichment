# UniHack Product Enrichment

Evidence-first product enrichment pipeline for the UniHack / Unilog industrial commerce challenge.

Given minimal distributor input (manufacturer part number, short description, brand placeholders), this project builds commerce-ready records that match the 252-column Unilog delivery format.

## Goals

- Manufacturer-first sourcing with marketplace blocklist
- Deterministic extraction before LLM fallback
- Category templates with fixed attribute slots
- Template-based descriptions (invoice, mobile, short, long, retail)
- Golden-row regression against provided expected output examples
- Confidence bands and validation reports

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Golden regression (target >= 70% field match)
python3 cli.py golden

# Enrich sample input
python3 cli.py enrich --limit 10

# Batch dishwasher rows with validation report
python3 cli.py batch --filter dishwasher --limit 20

# Run tests
pytest -q

# Run API
uvicorn app.main:app --reload
```

## Project layout

```text
app/                 FastAPI entrypoint and config
ingest/              CSV I/O and placeholder handling
identity/            Brand and manufacturer resolution
classify/            Category routing and templates
sources/             URL discovery and browser fetch fallback
extract/             HTML, PDF, cache, and desc parsing
normalize/           Attribute mapping
compose/             Descriptions and asset filenames
validate/            Rules, golden diff, batch reports
pipeline.py          Row enrichment orchestration
cli.py               Command line interface
data/evidence_cache/ Manufacturer evidence cache (seed + live updates)
guidelines/          Challenge input, expected output, solution guide
```

## Supported categories

| Category | Template | Source strategy |
|----------|----------|-----------------|
| Built-in dishwashers | `built_in_dishwasher` | Manufacturer HTML + PDF + evidence cache |
| Metal cut-off discs | `metal_cutoff_disc` | Part description parsing + brand routing |

## Commands

| Command | Purpose |
|---------|---------|
| `python3 cli.py golden` | Compare golden rows (PDSH4816AF, WDTS7024RZ) |
| `python3 cli.py enrich` | Batch enrich CSV |
| `python3 cli.py batch --filter dishwasher` | Enrich subset with JSON validation report |
| `uvicorn app.main:app --reload` | Upload and download API |

## Validation

Golden scoring compares non-empty expected fields only. Internal distributor IDs such as `PART_NUMBER` and `SKU - MY_PART_NUMBER` are not available in the input file and may remain blank.

Optional Playwright browser fetch is used when manufacturer pages return HTTP 403.

## License

MIT
