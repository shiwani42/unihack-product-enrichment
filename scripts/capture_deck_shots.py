#!/usr/bin/env python3
"""Capture retina stills of the live UI for the submission deck.

Usage:
    PYTHONPATH=. python3 scripts/capture_deck_shots.py [base_url]

Writes 2x device-scale PNGs to demo_build/deck_shots/. Element-scoped shots keep
each image tight around the thing it proves, so the deck never has to shrink a
full desktop screenshot down to illegible text. No fake cursor is injected.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo_build" / "deck_shots"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
VIEWPORT = {"width": 1440, "height": 900}
CHROME = "/usr/bin/google-chrome"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    with sync_playwright() as p:
        launch: dict = {"headless": True, "args": ["--hide-scrollbars"]}
        if Path(CHROME).exists():
            launch["executable_path"] = CHROME
        browser = p.chromium.launch(**launch)
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = ctx.new_page()

        def snap(name: str, selector: str | None = None, full: bool = False) -> None:
            target = page.locator(selector).first if selector else page
            kwargs = {"path": str(OUT / f"{name}.png")}
            if selector is None and full:
                kwargs["full_page"] = True
            target.screenshot(**kwargs)
            print(f"  {name}.png")

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_selector("#proof-band", state="visible", timeout=30000)
        page.wait_for_timeout(600)
        snap("hero")
        snap("proof_band", "#proof-band")

        page.click(".preset-pill:has-text('Frigidaire Dishwasher')")
        page.fill("#sb_mpn", "PDSH4816AF")
        page.fill("#sb_desc", "Built-In Dishwasher 24 in 49 dBA 120 V 15 A Leg")
        page.click("#sbEnrichBtn")
        page.wait_for_selector("#sb-result-container .spec-row", timeout=60000)
        page.wait_for_timeout(400)
        snap("record_panel", ".wb-output")
        snap("descriptions", ".desc-list")
        snap("attributes", ".spec-rows")
        snap("result_head", ".result-head")

        page.click(".preset-pill:has-text('Whirlpool Eco Dishwasher')")
        page.click("#sbEnrichBtn")
        page.wait_for_selector("#sb-result-container .spec-row", timeout=60000)
        page.wait_for_timeout(400)
        snap("record_panel_wp", ".wb-output")
        snap("descriptions_wp", ".desc-list")
        snap("attributes_wp", ".spec-rows")

        page.select_option("#sampleLimit", "100")
        page.click("#liveBtn")
        page.wait_for_function(
            "() => (document.getElementById('progress-message')||{}).textContent"
            "?.includes('Complete') === true",
            timeout=300000,
        )
        page.wait_for_timeout(500)
        snap("batch_progress", "#batch-progress")

        page.click('[data-page="catalog"]')
        page.wait_for_selector("#results-body tr[data-mpn]", timeout=60000)
        page.wait_for_timeout(500)
        snap("catalog_page", "#page-catalog")
        snap("catalog_toolbar", ".page-head-row")
        snap("export_group", ".page-actions")

        page.click("#results-body tr[data-mpn]")
        page.wait_for_selector("#drawer.open", timeout=30000)
        page.wait_for_timeout(400)
        snap("drawer_record", "#drawer")
        page.click('[data-dtab="evidence"]')
        page.wait_for_function(
            "() => document.querySelectorAll('#dtab-evidence a').length > 0",
            timeout=30000,
        )
        page.wait_for_timeout(400)
        snap("drawer_evidence", "#drawer")
        snap("evidence_panel", "#dtab-evidence")
        page.click('[data-dtab="audit"]')
        page.wait_for_timeout(600)
        snap("drawer_audit", "#drawer")

        ctx.close()
        browser.close()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
