# unilog enrichment engine

**Live app:** https://unilog-tau.vercel.app

**Evidence-first product intelligence for industrial commerce.** Six cryptic distributor
columns in, a validated, source-traced record in Unilog's 252-column delivery format out.

- **Demo film (3 min):** https://vimeo.com/1220615209 · reproducible build in `demo_build/`
- **Submission deck:** `submission/UniHack_thExplorers_Prototype.pptx`
- **Delivery artifacts:** `output/batch_enriched.csv` · `output/batch_enriched.xlsx` · `output/field_provenance.json`

## Measured results

| Metric | Result |
|---|---|
| Reference regression vs organizer expected output | **100%** — 134/134 fields, both reference SKUs (PDSH4816AF, WDTS7024RZ) |
| Input rows classified to a leaf category | **1000 / 1000** (14 templates: 13 leaves + generic industrial fallback) |
| Avg fields populated per row (full online batch) | **39.28** of the fields evidence supports; blank beats invented |
| Confidence bands | 29 high · 25 medium · 946 review — "high" requires external manufacturer evidence |
| Hermetic test suite | **176 tests**, offline by default |
| Compute cost | **≈ $0.0004/SKU** rules path (1000 rows ≈ 60s, zero API calls); LLM last-mile capped, off by default |

## How it works

```
Input CSV (6 cols: MPN, desc, brand placeholders)
  │
  ├─ ingest/        input analysis, placeholder filtering, dedup merge
  ├─ identity/      brand resolution: aliases → DIB/E1 → desc regex → MPN prefix rules
  ├─ classify/      leaf-level routing (rules + 14 templates, generic last)
  ├─ sources/       manufacturer-first URL discovery, marketplace blocklist,
  │                 cache-first fetch: retry/backoff, budget, optional Playwright on 403
  ├─ extract/       HTML specs · JSON-LD/microdata (extruct) · PDF datasheets
  │                 · evidence cache · honest desc parsing · optional LLM last-mile
  ├─ normalize/     units, LOV, canonical brand casing, attribute slot mapping
  ├─ compose/       5 governed descriptions + delivery-convention asset names
  ├─ validate/      LOV/char-limit/sanity rules, confidence bands, reference harness
  │
  └─ output/        252-col CSV/XLSX + per-value provenance JSON (source URL per cell)
```

Every populated value carries a **source URL** (`output/field_provenance.json`); the web UI
exposes it in a per-SKU provenance drawer. Values without external evidence cite
`input:Part_Desc` and can never reach the "high" confidence band.

## Integrity guarantees (enforced by tests)

- No fabricated values — blank beats invented; brand-name material invention removed
- `Actual Image (Yes/No)` is "Yes" only with verifiable manufacturer imagery evidence
- Amazon/eBay/Walmart/Home Depot/Lowe's/Target are blocked as sources
- Uniform cache-first fetch policy for every category; `UNILOG_LIVE_FETCH=0` kills network
- Explicit units preserved verbatim; bare numbers never auto-labeled volts

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=. python3 cli.py reference       # 100% deterministic, zero network (alias: golden)
PYTHONPATH=. pytest -q                      # hermetic tests, offline by default
PYTHONPATH=. python3 cli.py batch --filter all --xlsx --workers 4 \
    --provenance output/field_provenance.json
uvicorn app.main:app --port 8000            # web UI at http://localhost:8000
```

## What you can test on Vercel, and what needs a local clone

The hosted prototype is https://unilog-tau.vercel.app. You can open that URL without installing anything, pick a sample or drop your own six-column distributor CSV (`Mfg_Part_Num`, `Part_Desc`, `E1_Brand`, `Unilog_Brand`, `DIB_Brand`, `Part_Manuf`), run enrichment, watch rows land in Catalog, open a record for evidence and provenance, and download CSV, Excel, and the provenance file. That path is enough to see manufacturer-first fetch, classification, governed descriptions, and the 252-column delivery format. The sample catalog already in the repo is `guidelines/Unihack_ Sample Dataset - Input.csv`; on Vercel you use the Enrich page, and locally you can also pass `--input` to `cli.py batch` or drop the same CSV on the UI after `uvicorn`.

The hosted upload is only that product CSV. It cannot take the official Solution Guide workbooks from the hackathon Resources page (the large LOV, manufacturer and brand list, UOM abbreviations, inch fractions, taxonomy, and the 200-row gold file), because those files are far bigger than a serverless request is allowed to be, and even a smaller workbook that did get through would live on one function instance and disappear on the next. Fractions, UOM, and the 200-row file are small enough that an upload might reach a single function; the brand list and taxonomy are large enough that they would often time out; the 161k-row LOV is large enough that it usually never arrives at all. We did not put a second dropzone on the Vercel page for those tables, because it would look like it works and then fail for the files that actually matter. Without those workbooks the live app still runs, using the standards we mined from the gold sample and the 1,000-row input, then the small built-in JSON files. That is a real subset of LOV values, brand casing, UOM, and fractions, not a fake 14k taxonomy or a fake 161k LOV, and it is enough to judge the pipeline. It is not a substitute for Unilog’s official tables.

If you have downloaded the dashboard `.xlsx` files and you want official LOV checks, legal brand ®/™ casing, the full UOM list, the fraction table, extra taxonomy leaves, or the 200-row scorer, you need to clone this repo and run it on your machine (or put the workbooks in a deployment you control). Save them in `guidelines/references/` under the original names or close variants such as `Unicat_Lov_updated_….xlsx`, `FAUCETS_LOV.xlsx`, or `Fittings_LOV.xlsx`; `guidelines/` and `UNILOG_REFERENCES_DIR` are also scanned. Enrichment imports them automatically and overlays the mined JSON, so you do not have to classify each workbook or run the importer first. Do not put the six-column product CSV in `guidelines/references/`; that folder is only for Unilog standards. `UNILOG_INTERNAL_CONTENT_GUIDELINES.docx` is still not parsed, so description formulas stay the ones learned from the gold sample. More detail is in `guidelines/references/README.md`.

A full 1,000-row CLI batch with workers, resume, and checkpoint, plus `pytest`, is also local. The Vercel function enriches a small window per request (typically one SKU) so it does not time out, which is why the hosted demo is a live walkthrough rather than a dump of the whole sample in one click.

Manufacturer URLs show up when the live fetch actually reaches a product or literature page on the brand site (Hunter’s Shopify PDP for variant SKU 59243, Milwaukee `/products/details/…`, Frigidaire owner-center when that host answers). The Enrich dropzone still only takes the six-column CSV; we look up manufacturer hosts from the brand map and from on-site search, and we do not ask you to paste a MFR URL. If the manufacturer page never loads, or the part number is a distributor prefix the brand site does not use, or the brand is not in the map so there is no domain to start from, attributes and descriptions stay cited as `input:Part_Desc`. That is honest provenance, not a missing button. Blade span or finish can still say `Part_Desc` even when `MFR URL` is filled, if those values were already parsed from the distributor line and the manufacturer HTML did not repeat them as structured specs. A full pass over the 1,000-row sample, with every brand’s search templates, is `cli.py batch` on your machine; the hosted app is for walking SKUs, not for scraping the whole catalog in one request.

## Repository map

| Path | Purpose |
|---|---|
| `pipeline.py` | Row orchestration, fail-safe per row |
| `app/` | FastAPI + redesigned web UI (Enrich / Catalog; record drawer: Record / Evidence / Audit) |
| `scripts/` | measure, compliance, deck builder, artifact restore, reference importer |
| `demo_build/` | Reproducible 3-minute demo film (Remotion + verified UI capture) |
| `guidelines/` | Challenge input, expected output format, solution guide |
| `tests/` | Hermetic tests incl. integrity, uniform-fetch, units-honesty |

## License

MIT
