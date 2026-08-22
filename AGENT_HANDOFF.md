# Agent Handoff: UniHack Product Enrichment

This document is the single source of truth for any coding agent continuing work on this project.

**Repo path:** `/home/shiwani/a/code/hackathons/unilog`  
**GitHub:** https://github.com/shiwani42/unihack-product-enrichment  
**Hackathon deadline:** 23 Aug 2026, 11:59 PM IST

---

## 1. What this project does

Transforms **6-column distributor input** into **252-column Unilog delivery format** using a manufacturer-first enrichment pipeline.

| Input columns | `Mfg_Part_Num`, `Part_Desc`, `E1_Brand`, `Unilog_Brand`, `DIB_Brand`, `Part_Manuf` |
| Output | Fixed 252 headers from `guidelines/Unihack_ Expected Output - Delivery Format.csv` |

**Challenge rules (summary):**
- Primary source = manufacturer website (not Amazon/eBay)
- Leaf-level taxonomy + category attributes + LOV where applicable
- Five description types + marketing + item features from manufacturer
- Source URL traceability per populated value
- Full pipeline required (not mock UI only)
- Dynamic processing (not hardcoded for sample rows only)
- Accuracy is the top judging criterion (stated target: 100%; we benchmark against the organizer reference expected output)

Reference docs: `guidelines/challenge.txt`, `GUIDELINES_COMPLIANCE.md`, `IMPROVEMENT_LOG.md`

---

## 2. Quick start

```bash
cd /home/shiwani/a/code/hackathons/unilog
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Reference regression (must stay >= 70%, currently 100%)
PYTHONPATH=. python3 cli.py reference

# Full batch with provenance + XLSX
PYTHONPATH=. python3 cli.py batch --filter all --xlsx --provenance output/field_provenance.json

# Quality metrics (run before/after every change)
PYTHONPATH=. python3 scripts/measure.py
PYTHONPATH=. python3 scripts/measure.py --save latest
PYTHONPATH=. python3 scripts/measure.py --compare baseline latest

# Tests
PYTHONPATH=. pytest -q

# Web app
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000
# Open http://127.0.0.1:8000
```

---

## 3. Architecture

```
Input CSV (6 cols)
    │
    ▼
ingest/csv_io.py          Read/write CSV, empty row factory
    │
    ▼
identity/brand_resolver.py   DIB → E1 → Part_Desc regex → MPN prefix
    │
    ▼
classify/category_router.py  Rule-based routing (routing_rules.json) → JSON templates
    │
    ├── built_in_dishwasher ──► extract/html_specs.py (HTML+PDF+cache+extruct)
    ├── metal_cutoff_disc ────► extract/desc_parser.py
    └── remaining 12 templates ─► extract/generic_parser.py
                                  compose/generic_descriptions.py
    │
    ▼
normalize/mapper.py       Taxonomy + attribute slot filling
    │
    ▼
validate/rules.py         LOV, char limits, ecommerce URL block, attribute sanity
validate/reference_test.py Compare vs expected output rows
validate/report.py        Batch reports + field_sources + category_id
    │
    ▼
output/enriched.csv       252-column delivery file
output/field_provenance.json  Per-field source map (optional)
output/enriched.xlsx      XLSX delivery (optional)
```

**Orchestrator:** `pipeline.py` → `enrich_input_row()`  
**CLI:** `cli.py` (`enrich`, `reference`, `batch`)  
**API/UI:** `app/main.py` + `app/static/`

---

## 4. Current quality (latest, post Change #8)

| Metric | Baseline | Latest |
|--------|----------|--------|
| Reference avg | 95.6% | **100%** (deterministic, cache-first) |
| PDSH4816AF | 96.8% | **100%** (63/63) |
| WDTS7024RZ | 94.4% | **100%** (71/71) |
| Category coverage | 13.3% | **100%** |
| Batch avg fields (1000 rows) | 11.21 | **39.28** (honest count) |
| Tests passing | 2 | **77 hermetic (~2s)** |

See `GUIDELINES_COMPLIANCE.md` for requirement mapping.  
See `IMPROVEMENT_LOG.md` for change history.

Saved snapshots: `output/metrics/baseline.json`, `output/metrics/latest.json`

**Reference MPNs:** `PDSH4816AF`, `WDTS7024RZ` (defined in `app/config.py`); served entirely from documented seed caches in `data/evidence_cache/` — reference runs never touch the network.

**Known reference gaps:** `PART_NUMBER` and `SKU - MY_PART_NUMBER` are not in input and stay blank by design.

**Integrity rules (Change #8):**
- No fabricated values: blank beats invented; defaults like "Hardwired"/"Aluminum Oxide" by brand name were removed
- Confidence "high" requires externally verified evidence (`pipeline.count_verified_items`)
- Uniform fetch policy: every category gets identical live-fetch opportunity (`UNILOG_FETCH_BUDGET` caps attempts per process; `UNILOG_LIVE_FETCH=0` disables network)

---

## 5. Supported categories (14 templates)

| Template ID | Coverage strategy |
|-------------|-------------------|
| `built_in_dishwasher` | Mfr HTML/PDF + evidence cache |
| `metal_cutoff_disc` | Part_Desc regex (abrasives) |
| `sanding_abrasive` | Part_Desc (belts, discs, sandpaper) |
| `grinding_wheel` | Part_Desc |
| `led_lighting` | Part_Desc + Kichler/Satco identity |
| `electrical_box` | Part_Desc (box covers) |
| `ceiling_fan` | Part_Desc + Hunter identity |
| `cooking_range` | Part_Desc + GE/Cafe prefix |
| `power_tool_accessory` | Part_Desc (drill bits, blades) |
| `deck_composite` | Part_Desc (Trex / AZEK / fascia) |
| `building_trim` | Part_Desc |
| `wire_cable` | Part_Desc |
| `pipe_fitting` | Part_Desc |
| `generic_industrial` | **Fallback for all remaining rows** |

Routing rules: `classify/routing_rules.json` (ordered, first match wins; generic last).

---

## 6. Key files map

| Path | Purpose |
|------|---------|
| `pipeline.py` | Main enrichment orchestration; returns `field_sources` |
| `identity/brand_resolver.py` | Brand/manufacturer resolution |
| `identity/mpn_prefix_rules.json` | APPDE MPN prefix → brand |
| `identity/manufacturer_map.json` | Brand → mfr name, domains |
| `extract/html_specs.py` | Live fetch + regex; reference SKUs served from seed caches |
| `extract/structured.py` | **extruct** JSON-LD/microdata extraction |
| `extract/cache.py` | Evidence cache read/write |
| `data/evidence_cache/*.json` | Seeded manufacturer evidence |
| `extract/desc_parser.py` | Abrasive parsing from description |
| `extract/pdf_specs.py` | PDF spec extraction |
| `sources/browser_fetcher.py` | httpx + optional Playwright on 403 |
| `sources/finder.py` | Manufacturer URL candidates + ecommerce blocklist |
| `compose/descriptions.py` | Dishwasher description builders |
| `validate/reference_test.py` | Field-level reference diff |
| `validate/report.py` | Batch summary + per-row `field_sources` |
| `scripts/measure.py` | **Mandatory** before/after quality measurement |
| `app/main.py` | FastAPI + SSE stream + reference API |
| `app/static/` | Unilog web UI (Enrich / Catalog) |

---

## 7. Agent rules: only keep improving changes

1. **Always run metrics before and after:**
   ```bash
   PYTHONPATH=. python3 scripts/measure.py --save latest
   PYTHONPATH=. python3 scripts/measure.py --compare baseline latest
   ```
   (Offline-deterministic by default; use `--online` after prewarming caches.)
2. **NEVER merge a change that lowers `reference.average_pct`** (currently **100%**).
3. **NEVER reintroduce fabricated values**: no brand-name material invention, no invented defaults, no unverified "Actual Image = Yes". Blank beats wrong.
4. **Keep the fetch policy uniform**: do not special-case categories for live fetching; budgets/timeouts are the only knobs.
5. **Prefer changes that improve:** verified-evidence counts, per-category filled-field parity, reference per-MPN scores.
6. **Log every kept/reverted change** in `IMPROVEMENT_LOG.md`.
7. **Run `pytest -q`** after pipeline changes (hermetic; mark network tests with `@pytest.mark.network`).
8. **Do not hardcode** evaluation SKUs beyond the two documented reference seed rows.
9. **Minimize scope** — one improvement at a time, measure, keep or revert.

---

## 8. Improvement backlog (remaining)

### Not yet fully solved
- [ ] Full 14,000-leaf taxonomy mapping (currently keyword templates + 22 indexed leaves)
- [ ] Complete LOV from solution guide reference files
- [ ] Prewarm evidence caches for a diverse per-category sample (abrasives/LED/fan/boxes) to lift verified coverage
- [ ] `PART_NUMBER` / `SKU - MY_PART_NUMBER` (not in input CSV)
- [ ] Per-field source columns inside 252-col CSV (use provenance JSON instead)
- [ ] Optional: rapidfuzz brand-alias matching, trafilatura HTML cleaning, semantic taxonomy matching

### Done in Change #8
- [x] Uniform live fetch for all categories (incl. generic_industrial)
- [x] Retry/backoff, atomic writes, raw-cache eviction/TTL
- [x] Dedup merge instead of drop; API event-loop fixes
- [x] Honest confidence bands + empty-description validation
- [x] Hermetic test suite

---

## 9. Web UI

**URL:** http://127.0.0.1:8000 (when uvicorn running)

Screens: **Enrich** (hero with reference proof band, single-row sandbox with presets, batch stream with honest progress — bar + counters, log behind a "Details" disclosure) and **Catalog** (search/filter, per-row drawer, export group: CSV / XLSX / Provenance). Hash-routed: `#/enrich`, `#/catalog`, `#/record/<mpn>` (deep-linkable drawer).

The record drawer has three tabs — **Record** (input→output diff, descriptions, attributes, storefront preview), **Evidence** (manufacturer sources + honest-blanks statement) and **Audit** (validation findings + raw 252-column record). Escape closes it; focus is trapped and restored.

API endpoints:
- `GET /api/presets` — sample SKUs for the sandbox
- `GET /api/reference` — reference benchmark scores (feeds the proof band; hidden on failure, never hardcoded)
- `GET /api/taxonomy` — category templates (feeds the catalog filter)
- `GET /api/last-run` — persisted batch results
- `GET /api/enrich/stream?limit=5&filter=dishwasher` — SSE live enrichment
- `POST /api/enrich/single`, `POST /enrich/sample`, `POST /enrich` — single / sample batch / uploaded-file batch
- `GET /download/latest` (or `/download/csv`), `/download/xlsx`, `/download/provenance` — delivery artifacts

---

## 10. Evidence cache strategy

For manufacturer pages that timeout or return 403:
1. Live fetch attempted (httpx → Playwright fallback)
2. Merged with `data/evidence_cache/{MPN}.json` if live evidence thin
3. Reference SKUs (`PDSH4816AF`, `WDTS7024RZ`) have rich cache files

To seed cache for a new MPN:
```bash
# Run enrichment once, cache auto-saves when live items >= 5
PYTHONPATH=. python3 -c "
from pipeline import enrich_input_row
from ingest.csv_io import load_output_headers, read_input_rows
from app.config import DEFAULT_INPUT
headers = load_output_headers()
row = next(r for r in read_input_rows(DEFAULT_INPUT) if r['Mfg_Part_Num']=='YOUR_MPN')
enrich_input_row(row, headers)
"
```

---

## 11. Open-source tools in use / to adopt

| Tool | Status | Use |
|------|--------|-----|
| extruct | **Integrated** (`extract/structured.py`) | JSON-LD/microdata |
| pdfplumber | Integrated | PDF specs |
| Playwright | Optional | 403 bypass |
| httpx + BeautifulSoup | Integrated | HTTP fetch |
| openpyxl | **Integrated** | Delivery-format XLSX (`--xlsx`, `/download/xlsx`) |
| trafilatura | Not yet | Cleaner HTML text |
| Great Expectations | Not yet | Batch data quality |
| sentence-transformers | Not yet | Taxonomy matching |

---

## 12. Testing

```bash
PYTHONPATH=. pytest -q   # hermetic, ~2s; live fetch disabled via tests/conftest.py
```

Tests are offline by default. To test network behavior, mark with `@pytest.mark.network`.

| Test file | Asserts |
|-----------|---------|
| `tests/test_reference.py` | Reference MPNs 100% field match (floor 70%) |
| `tests/test_abrasive.py` | Metal cut-off disc routes and enriches |
| `tests/test_integrity.py` | No fabricated values (material/plug/series/image) |
| `tests/test_reliability.py` | Atomic writes, retry, eviction, loop safety |
| `tests/test_dedup_merge.py` | Duplicate rows merge, never drop |
| `tests/test_uniform_fetch.py` | Uniform fetch policy + honest bands |
| `tests/test_units_honesty.py` | Explicit units preserved, no invented labels |
| `tests/test_api.py` | FastAPI health, reference, enrich, downloads |
| `tests/test_coverage.py` / `test_validation.py` / `test_export.py` | Routing coverage, LOV/limits, CSV/XLSX/provenance |

Add tests in `tests/` for any new category template or resolver logic.

---

## 13. Submission checklist

- [x] `PYTHONPATH=. python3 cli.py reference` — **100%** (63/63 + 71/71)
- [x] Full 1000-row batch + provenance + XLSX in `output/`
- [x] Live prototype: https://unilog-tau.vercel.app
- [x] Demo film (3 min): https://vimeo.com/1220615209 · local `demo_build/demo.mp4`
- [x] Deck: `submission/UniHack_thExplorers_Prototype.pptx`
- [x] GitHub: https://github.com/shiwani42/unihack-product-enrichment
- [x] 77 hermetic tests passing

---

## 14. Contact / context

Built for UniHack / Unilog industrial commerce challenge.  
Judges care about: **accuracy**, full pipeline, manufacturer sourcing, validation, working prototype.

When in doubt: **measure first, change small, keep only what improves metrics.**
