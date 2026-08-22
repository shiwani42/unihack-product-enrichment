# UniHack Product Enrichment

Evidence-first product enrichment pipeline for the UniHack / Unilog industrial commerce challenge.

Given minimal distributor input (manufacturer part number, short description, brand placeholders), this project builds commerce-ready records that match the 252-column Unilog delivery format.

## Goals

- Manufacturer-first sourcing with marketplace blocklist
- Uniform cache-first live fetch policy for every category (no category bias)
- Deterministic extraction before LLM fallback; no fabricated values — blank beats invented
- Category templates with fixed attribute slots
- Template-based descriptions (invoice, mobile, short, long, retail)
- Golden-row regression against provided expected output examples
- Honest confidence bands: only externally verified evidence can score "high"
- Reliability primitives: retry/backoff, atomic cache writes, raw-cache eviction, per-run fetch budget
- Hermetic test suite (offline by default)

## Quick start

See **`AGENT_HANDOFF.md`** for full agent/developer documentation, metrics workflow, and improvement rules.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Golden regression (100% on both reference SKUs, cache-first, no network needed)
python3 cli.py golden

# Build taxonomy index and distributor crosswalk
PYTHONPATH=. python3 scripts/build_taxonomy_index.py
PYTHONPATH=. python3 scripts/build_crosswalk.py

# Pre-warm manufacturer evidence cache (run before online batch)
PYTHONPATH=. python3 scripts/prewarm_cache.py --filter branded --workers 4

# Full batch with dedup merge + parallel workers
PYTHONPATH=. python3 cli.py enrich --dedupe --workers 4 --xlsx --provenance output/field_provenance.json

# Optional LLM fallback for cryptic rows with unknown brand (off by default)
export UNILOG_LLM_ENABLED=1
export OPENAI_API_KEY=sk-your-key
export UNILOG_LLM_MODEL=gpt-4o-mini   # cheapest; ~$0.02 for 50 rows
export UNILOG_LLM_MAX_CALLS=50        # hard cap per run
PYTHONPATH=. python3 cli.py enrich --limit 50

# Run tests (hermetic, offline by default; ~2s)
pytest -q

# Measure quality (offline-deterministic by default)
PYTHONPATH=. python3 scripts/measure.py --compare baseline latest

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

Integrity rules enforced by the pipeline:
- Values without manufacturer/cache evidence cite `input:Part_Desc` and can never reach the "high" confidence band
- `Actual Image (Yes/No)` is "Yes" only when verifiable manufacturer imagery evidence exists
- Live fetching is uniform across categories, cache-first, budgeted (`UNILOG_FETCH_BUDGET`, default 150), with kill switch (`UNILOG_LIVE_FETCH=0`)

Optional Playwright browser fetch is used when manufacturer pages return HTTP 403.

## License

MIT
