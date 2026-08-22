# unilog enrichment engine

**Evidence-first product intelligence for industrial commerce.** Six cryptic distributor
columns in — a validated, source-traced record in Unilog's 252-column delivery format out.

- **Live prototype:** https://unilog-tau.vercel.app
- **Demo film (3 min):** https://vimeo.com/1220615209 · reproducible build in `demo_build/`
- **Submission deck:** `submission/UniHack_thExplorers_Prototype.pptx`
- **Delivery artifacts:** `output/batch_enriched.csv` · `output/batch_enriched.xlsx` · `output/field_provenance.json`

## Measured results

| Metric | Result |
|---|---|
| Golden regression vs organizer expected output | **100%** — 134/134 fields, both reference SKUs (PDSH4816AF, WDTS7024RZ) |
| Input rows classified to a leaf category | **1000 / 1000** (13 leaf templates + generic industrial fallback) |
| Avg fields populated per row (full online batch) | **39.28** of the fields evidence supports; blank beats invented |
| Confidence bands | 29 high · 25 medium · 946 review — "high" requires external manufacturer evidence |
| Hermetic test suite | **77 tests, ~2s**, offline by default |
| Compute cost | **≈ $0.0004/SKU** rules path (1000 rows ≈ 60s, zero API calls); LLM last-mile capped, off by default |

## How it works

```
Input CSV (6 cols: MPN, desc, brand placeholders)
  │
  ├─ ingest/        input analysis, placeholder filtering, dedup merge
  ├─ identity/      brand resolution: aliases → DIB/E1 → desc regex → MPN prefix rules
  ├─ classify/      leaf-level routing (rules + templates, 13 categories)
  ├─ sources/       manufacturer-first URL discovery, marketplace blocklist,
  │                 cache-first fetch: retry/backoff, budget, optional Playwright on 403
  ├─ extract/       HTML specs · JSON-LD/microdata (extruct) · PDF datasheets
  │                 · evidence cache · honest desc parsing · optional LLM last-mile
  ├─ normalize/     units, LOV, canonical brand casing, attribute slot mapping
  ├─ compose/       5 governed descriptions + delivery-convention asset names
  ├─ validate/      LOV/char-limit/sanity rules, confidence bands, golden harness
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

PYTHONPATH=. python3 cli.py golden          # 100% deterministic, zero network
PYTHONPATH=. pytest -q                      # 77 hermetic tests, ~2s
PYTHONPATH=. python3 cli.py batch --filter all --xlsx --workers 4 \
    --provenance output/field_provenance.json
uvicorn app.main:app --port 8000            # web UI at http://localhost:8000
```

Deployed on Vercel (`vercel.json`, `api/index.py`): offline mode, delivery artifacts seeded,
SSE live-enrichment stream, per-value provenance drawer, CSV/XLSX/provenance downloads.

## Repository map

| Path | Purpose |
|---|---|
| `pipeline.py` | Row orchestration, fail-safe per row |
| `app/` | FastAPI + redesigned web UI (Enrich / Batch / Catalog / Quality / Export) |
| `scripts/` | measure, compliance, deck builder, artifact restore, reference importer |
| `demo_build/` | Reproducible 3-minute demo film (Remotion + verified UI capture) |
| `guidelines/` | Challenge input, expected output format, solution guide |
| `tests/` | 77 hermetic tests incl. integrity, uniform-fetch, units-honesty |

## License

MIT
