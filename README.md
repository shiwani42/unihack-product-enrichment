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

# Enrich sample input (limit optional)
python cli.py enrich --limit 10

# Score against golden dishwasher examples
python cli.py golden

# Run API
uvicorn app.main:app --reload
```

## Project layout

```text
app/           FastAPI entrypoint and config
ingest/        CSV I/O and placeholder handling
identity/      Brand and manufacturer resolution
classify/      Category routing and templates
sources/       URL discovery helpers
extract/       HTML evidence extraction
normalize/     Attribute mapping
compose/       Description builders
validate/      Rules and golden diff
pipeline.py    Row enrichment orchestration
cli.py         Command line interface
guidelines/    Challenge input, expected output, solution guide
```

## Current scope

Phase 1 focuses on built-in dishwashers:

- APPDE rows in the sample input
- Golden examples: `PDSH4816AF`, `WDTS7024RZ`
- Fixed dishwasher attribute template from expected output

Next phases add PDF page-finder extraction, browser fetching for blocked sites, and additional category templates.

## Commands

| Command | Purpose |
|---------|---------|
| `python cli.py enrich --input guidelines/Unihack_\ Sample\ Dataset\ -\ Input.csv` | Batch enrich |
| `python cli.py golden` | Compare golden rows |
| `uvicorn app.main:app --reload` | Upload and download API |

## Validation

Golden scoring compares non-empty expected fields only. A row with missing manufacturer fetch still reports partial matches and missing fields separately.

## License

MIT
