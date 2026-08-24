# Unilog

Unilog fills a product catalog row from a distributor input table. It starts with manufacturer pages, never fetches shopping hosts, and cites a source URL for every filled cell. Blank beats invented.

App: https://unilog-tau.vercel.app

Demo: https://vimeo.com/1220615209

## How it works

<p align="center">
  <img src="./docs/diagrams/pipeline.png" alt="How one SKU is enriched: input table through identity, host discovery, fetch, and extract into a sourced catalog row. Wikidata, Firecrawl, Brave Search, DuckDuckGo, Bing, httpx, and Playwright sit on the path." width="100%">
</p>

<p align="center">
  <img src="./docs/diagrams/source-policy.png" alt="Evidence order: manufacturer site, family literature, third-party catalogs, distributors last. Shopping never." width="100%">
</p>

Figure sources: `docs/diagrams/*.svg` and `docs/diagrams/*.excalidraw`.

`enrich_input_row` in `pipeline.py` is the entry the app and `cli.py batch` both call. Pasting input does not replay a precooked CSV.

## Results

| Metric | Result |
|---|---|
| Reference SKUs | 134/134 fields on `PDSH4816AF` and `WDTS7024RZ` |
| Rows classified | 1000 / 1000 |
| Avg filled fields (live 1000-row batch) | 54.35 |
| Confidence (live batch) | 460 high, 520 medium, 20 review |
| Tests | hermetic, network off unless a test opts in |

High confidence needs an external manufacturer URL. `input:Part_Desc` cannot be high.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=. python3 cli.py reference
PYTHONPATH=. pytest -q
PYTHONPATH=. python3 cli.py batch
uvicorn app.main:app
```

Open http://localhost:8000 for the local UI. `UNILOG_LIVE_FETCH=1` (default on the hosted app) hits manufacturer pages. `UNILOG_LIVE_FETCH=0` turns the network off.

Web search tries **Firecrawl keyless** first (`POST /v2/search`, no API key), then Brave / DuckDuckGo / Bing. Optional `FIRECRAWL_API_KEY` raises rate limits if keyless is blocked. Set `UNILOG_FIRECRAWL=0` to skip it.

## Try it

The hosted app accepts a distributor product CSV, one SKU per request. Sample input lives in `guidelines/`.

Official LOV, brand, UOM, and taxonomy workbooks are local. Drop them in `guidelines/references/` (see that folder's README). The hosted app uses the mined subset in `data/reference/`.

A 1000-row batch with workers is `cli.py batch` on your machine. `cli.py harvest-brands` learns `{mpn}` URL shapes for brands that are not mapped yet.

## Repo

| Path | What |
|---|---|
| `pipeline.py` | `enrich_input_row` |
| `docs/diagrams/` | Architecture figures |
| `app/` | FastAPI plus Enrich and Catalog UI |
| `identity/` | Brand and manufacturer |
| `sources/` | URL discovery and fetch order |
| `extract/` | HTML, JSON-LD, PDF, desc parse |
| `compose/` | Descriptions and asset names |
| `validate/` | LOV, units, confidence |
| `demo_build/` | Demo film |
| `guidelines/` | Sample input and headers |

## License

MIT
