#!/usr/bin/env python3
"""Record the canonical unilog walkthrough against http://localhost:8000.

One continuous 1920x1080 Playwright recording of real interactions with a
visible cursor, semantic state checks between beats, then conversion to an
exact-frame CFR H.264 asset validated with scripts/validate_recording.py.
Segment boundaries (recording-relative seconds) land in
recordings/walkthrough_meta.json for the Remotion storyboard and tests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BUILD = Path(__file__).resolve().parent
RECORDINGS = BUILD / "recordings"
SCREENSHOTS = BUILD / "screenshots"
PLAN_PATH = BUILD / "interaction_plan.json"
BASE_URL = "http://localhost:8000"
VIEWPORT = {"width": 1920, "height": 1080}
FPS = 30
CHROME = "/usr/bin/google-chrome"

CURSOR_JS = r"""
(() => {
  const el = document.createElement('div');
  el.id = '__demo_cursor';
  el.style.cssText = [
    'position:fixed', 'left:50%', 'top:50%', 'width:30px', 'height:30px',
    'margin:-15px 0 0 -15px', 'border-radius:50%',
    'border:3px solid #12b76a', 'background:rgba(18,183,106,0.22)',
    'box-shadow:0 0 14px rgba(18,183,106,0.6)', 'z-index:2147483647',
    'pointer-events:none'
  ].join(';');
  const dot = document.createElement('div');
  dot.style.cssText = [
    'position:absolute', 'left:50%', 'top:50%', 'width:8px', 'height:8px',
    'margin:-4px 0 0 -4px', 'border-radius:50%', 'background:#12b76a'
  ].join(';');
  el.appendChild(dot);
  let pos = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
  const paint = () => { el.style.left = pos.x + 'px'; el.style.top = pos.y + 'px'; };
  window.__unilogCursorMove = (x, y, ms) => new Promise((resolve) => {
    const sx = pos.x, sy = pos.y;
    if (ms <= 0 || (sx === x && sy === y)) { pos = { x, y }; paint(); resolve(true); return; }
    const t0 = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - t0) / ms);
      const e = 1 - Math.pow(1 - p, 3);
      pos = { x: sx + (x - sx) * e, y: sy + (y - sy) * e };
      paint();
      if (p < 1) requestAnimationFrame(step); else resolve(true);
    };
    requestAnimationFrame(step);
  });
  const attach = () => { document.body.appendChild(el); paint(); };
  if (document.body) attach();
  document.addEventListener('DOMContentLoaded', attach);
})();
"""


class Recorder:
    def __init__(self, page: Page):
        self.page = page
        self.t0 = time.monotonic()
        self.segments: dict[str, dict] = {}
        self.actions: list[dict] = []
        self._open_at: str | None = None

    def now(self) -> float:
        return round(time.monotonic() - self.t0, 3)

    def open_segment(self, seg_id: str):
        if self._open_at is not None:
            self.close_segment(self._open_at)
        self._open_at = seg_id
        self.segments.setdefault(seg_id, {})["start"] = self.now()

    def close_segment(self, seg_id: str | None = None):
        seg_id = seg_id or self._open_at
        assert seg_id is not None, "no segment open"
        self.segments[seg_id]["end"] = self.now()
        self._open_at = None

    def log_action(self, label: str, **extra):
        entry = {"label": label, "t": self.now(), **extra}
        self.actions.append(entry)
        print(f"  [{entry['t']:7.2f}s] {label}")


def settle(seconds: float):
    time.sleep(seconds)


def move_cursor(page: Page, x: float, y: float, ms: int = 520):
    page.evaluate("([x, y, ms]) => window.__unilogCursorMove(x, y, ms)", [x, y, ms])


def click_element(page: Page, rec: Recorder, selector: str, label: str):
    loc = page.locator(selector).first
    loc.wait_for(state="visible", timeout=15000)
    try:
        loc.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    box = loc.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    move_cursor(page, cx, cy)
    settle(0.28)
    page.mouse.click(cx, cy)
    rec.log_action(label, target=selector, x=round(cx), y=round(cy))


def type_field(page: Page, rec: Recorder, selector: str, value: str, label: str):
    click_element(page, rec, selector, f"focus-{label}")
    page.keyboard.type(value, delay=48)
    rec.log_action(label, target=selector, typed=value)
    settle(0.45)


def smooth_scroll(page: Page, selector: str, distance: int, steps: int = 6):
    page.evaluate(
        """([sel, dist, steps]) => {
             const el = document.querySelector(sel);
             const target = el || window;
             const per = dist / steps;
             return new Promise((resolve) => {
               let i = 0;
               const iv = setInterval(() => {
                 i += 1;
                 if (el) el.scrollBy({ top: per, behavior: 'smooth' });
                 else window.scrollBy({ top: per, behavior: 'smooth' });
                 if (i >= steps) { clearInterval(iv); resolve(true); }
               }, 260);
             });
           }""",
        [selector, distance, steps],
    )


def wait_nonempty(page: Page, selector: str, timeout_ms: int = 20000):
    page.wait_for_function(
        "([sel]) => { const el = document.querySelector(sel);"
        "return el && el.innerText.trim().length > 0; }",
        arg=[selector],
        timeout=timeout_ms,
    )


def run_walkthrough(record_video: bool) -> tuple[Path, dict]:
    plan = json.loads(PLAN_PATH.read_text())
    RECORDINGS.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    tmp_profile = Path("/tmp/opencode/unilog-demo-profile")
    if tmp_profile.exists():
        shutil.rmtree(tmp_profile)
    tmp_profile.mkdir(parents=True)

    raw_dir = RECORDINGS / "_raw_take"
    if record_video and raw_dir.exists():
        shutil.rmtree(raw_dir)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--force-device-scale-factor=1", "--hide-scrollbars"],
        )
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(raw_dir) if record_video else None,
            record_video_size=VIEWPORT if record_video else None,
            accept_downloads=True,
        )
        context.add_init_script(CURSOR_JS)
        page = context.new_page()
        rec = Recorder(page)

        # ---- Beat 1: hero -------------------------------------------------
        rec.open_segment("seg-hero")
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_selector("text=Six columns in.", timeout=20000)
        rec.log_action("load-hero")
        wait_nonempty(page, "#presets-list")
        page.wait_for_selector("#proof-band", state="visible", timeout=20000)
        rec.log_action("proof-band-visible")
        settle(5.5)
        rec.close_segment()

        # ---- Beat 2: enrich form ------------------------------------------
        rec.open_segment("seg-enrich")
        type_field(page, rec, "#sb_mpn", "PDSH4816AF", "type-mpn")
        type_field(page, rec, "#sb_desc", "24in built-in dishwasher", "type-desc")
        settle(0.8)
        click_element(page, rec, "#sbEnrichBtn", "click-enrich")
        page.wait_for_selector("#sb-result-container .wb-empty", state="detached", timeout=30000)
        wait_nonempty(page, "#sb-result-container")
        page.wait_for_timeout(600)
        rec.log_action("result-panel-visible")
        settle(3.0)
        smooth_scroll(page, ".wb-output", 420)
        settle(2.5)
        rec.close_segment()

        # ---- Beat 3: catalog + drawer evidence ------------------------------
        rec.open_segment("seg-catalog-drawer")
        click_element(page, rec, "[data-page=\"catalog\"]", "nav-catalog")
        page.wait_for_selector("#results-body tr[data-mpn]", timeout=20000)
        settle(3.5)
        click_element(page, rec, "#results-body tr[data-mpn]", "open-drawer")
        page.wait_for_selector("#drawer.open", timeout=10000)
        wait_nonempty(page, "#drawerMpn")
        settle(1.6)
        click_element(page, rec, "[data-dtab=\"evidence\"]", "tab-evidence")
        wait_nonempty(page, "#dtab-evidence")
        page.wait_for_function(
            "() => document.querySelectorAll('#dtab-evidence a').length > 0",
            timeout=10000,
        )
        rec.log_action("evidence-visible")
        settle(3.2)
        smooth_scroll(page, ".drawer-body", 380)
        settle(2.4)
        page.keyboard.press("Escape")
        rec.log_action("close-drawer-esc")
        settle(1.6)
        rec.close_segment()

        # ---- Beat 4: batch stream ------------------------------------------
        rec.open_segment("seg-batch")
        click_element(page, rec, "[data-page=\"enrich\"]", "nav-batch")
        settle(1.8)
        page.select_option("#sampleLimit", "1000")
        rec.log_action("set-limit-1000")
        settle(0.9)
        click_element(page, rec, "#liveBtn", "click-run-batch")
        page.wait_for_function(
            "() => (document.getElementById('progress-message')||{}).textContent"
            "?.includes('Complete') === true",
            timeout=240000,
        )
        rec.log_action("batch-complete")
        settle(5.0)
        rec.close_segment()

        # ---- Beat 5: golden proof band --------------------------------------
        rec.open_segment("seg-proof")
        smooth_scroll(page, None, -900)
        settle(2.4)
        page.wait_for_selector("#proof-band", state="visible", timeout=10000)
        rec.log_action("proof-band-shown")
        settle(1.8)
        click_element(page, rec, "#proof-band button", "click-golden-sku")
        page.wait_for_selector("#sb-result-container .skeleton", state="detached", timeout=30000)
        wait_nonempty(page, "#sb-result-container")
        rec.log_action("golden-sku-enriched")
        settle(3.2)
        rec.close_segment()

        # ---- Beat 6: export CSV from catalog ---------------------------------
        rec.open_segment("seg-export")
        click_element(page, rec, "[data-page=\"catalog\"]", "nav-catalog-export")
        page.wait_for_selector("#results-body tr[data-mpn]", timeout=20000)
        settle(1.6)
        csv_row = page.locator(".export-group a[href=\"/download/csv\"]").first
        box = csv_row.bounding_box()
        move_cursor(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        settle(0.35)
        artifacts = BUILD / "artifacts"
        artifacts.mkdir(exist_ok=True)
        with page.expect_download(timeout=30000) as dl:
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            rec.log_action("click-csv-download")
        download = dl.value
        download.save_as(str(artifacts / "delivery_export.csv"))
        rec.log_action("download-saved", file=download.suggested_filename)
        settle(3.4)
        rec.close_segment()

        settle(0.8)
        video_path = None
        if record_video:
            video_path = page.video.path()
        context.close()
        browser.close()

    meta = {
        "base_url": BASE_URL,
        "viewport": VIEWPORT,
        "fps": FPS,
        "output": plan["output"],
        "raw_output": plan["raw_output"],
        "segments": rec.segments,
        "actions": rec.actions,
    }
    return Path(video_path), meta


def convert_to_cfr(raw_webm: Path, out_mp4: Path) -> float:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(raw_webm),
            "-vf", f"fps={FPS}", "-c:v", "libx264", "-preset", "medium",
            "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out_mp4),
        ],
        check=True,
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames:format=duration",
         "-of", "json", str(out_mp4)],
        check=True, capture_output=True, text=True,
    )
    info = json.loads(probe.stdout)
    frames = int(info["streams"][0]["nb_read_frames"])
    duration = round(frames / FPS, 3)
    return duration


def capture_screenshots():
    """Separate no-video pass producing canonical stills for fallback/stills."""
    shots = {
        "hero.png": ("#proof-band", None),
        "enrich_result.png": ("#sb-result-container .spec-row", None),
        "catalog_table.png": ("#results-body tr[data-mpn]", None),
        "drawer_evidence.png": ("#dtab-evidence.active", None),
        "proof_band.png": ("#proof-band", None),
        "catalog_export.png": (".export-group", None),
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True)
        ctx = browser.new_context(viewport=VIEWPORT, accept_downloads=True)
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()
        page.goto(BASE_URL, wait_until="networkidle")

        def shot(name, sel, pre=None):
            page.wait_for_selector(sel, timeout=20000)
            if pre:
                pre()
                page.wait_for_timeout(800)
            page.screenshot(path=str(SCREENSHOTS / name))
            print(f"  screenshot {name}")

        shot("hero.png", "#proof-band",
             pre=lambda: page.wait_for_timeout(900))
        page.fill("#sb_mpn", "PDSH4816AF")
        page.fill("#sb_desc", "24in built-in dishwasher")
        page.click("#sbEnrichBtn")
        shot("enrich_result.png", "#sb-result-container .spec-row",
             pre=lambda: page.wait_for_selector(
                 "#sb-result-container .wb-empty", state="detached", timeout=30000))
        page.click("[data-page=\"catalog\"]")
        shot("catalog_table.png", "#results-body tr[data-mpn]",
             pre=lambda: page.wait_for_timeout(900))
        page.click("#results-body tr[data-mpn]")
        page.click("[data-dtab=\"evidence\"]")
        shot("drawer_evidence.png", "#dtab-evidence.active",
             pre=lambda: page.wait_for_function(
                 "() => document.querySelectorAll('#dtab-evidence a').length > 0"))
        page.keyboard.press("Escape")
        page.click("[data-page=\"enrich\"]")
        page.evaluate("window.scrollTo(0, 0)")
        page.click("#proof-band button")
        shot("proof_band.png", "#sb-result-container .result-head",
             pre=lambda: page.wait_for_selector(
                 "#sb-result-container .skeleton", state="detached", timeout=30000))
        page.click("[data-page=\"catalog\"]")
        shot("catalog_export.png", ".export-group",
             pre=lambda: page.wait_for_timeout(600))
        ctx.close()
        browser.close()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"
    record = mode in ("--all", "--record")
    do_shots = mode in ("--all", "--screens")

    if record:
        print("[1/3] recording walkthrough ...")
        raw_path, meta = run_walkthrough(record_video=True)
        raw_files = sorted(Path(RECORDINGS / "_raw_take").glob("*.webm")) or [raw_path]
        raw = raw_files[-1]
        raw_final = RECORDINGS / meta["raw_output"]
        shutil.move(str(raw), raw_final)
        shutil.rmtree(RECORDINGS / "_raw_take", ignore_errors=True)
        print("[2/3] converting to CFR mp4 ...")
        mp4 = RECORDINGS / meta["output"]
        duration = convert_to_cfr(raw_final, mp4)
        meta["duration_s"] = duration
        last_end = max(seg["end"] for seg in meta["segments"].values())
        if last_end > duration:
            scale = duration / last_end
            for seg in meta["segments"].values():
                seg["start"] = round(seg["start"] * scale, 3)
                seg["end"] = round(seg["end"] * scale, 3)
        tail = min(seg["end"] for seg in meta["segments"].values())
        first_start = min(seg["start"] for seg in meta["segments"].values())
        assert abs(first_start) < 0.001, "first segment must start at 0"
        # make segments contiguous across gaps (gaps belong to preceding hold)
        ordered = sorted(meta["segments"].items(), key=lambda kv: kv[1]["start"])
        for (_, seg), (_, nxt) in zip(ordered, ordered[1:]):
            seg["end"] = nxt["start"]
        ordered[-1][1]["end"] = duration
        (RECORDINGS / "walkthrough_meta.json").write_text(json.dumps(meta, indent=2))
        print(f"[3/3] validating {mp4.name} ...")
        subprocess.run(
            [sys.executable, str(BUILD / "scripts" / "validate_recording.py"),
             str(mp4), "--fps", "30", "--duration", str(duration)],
            check=True,
        )
        print(f"meta: {RECORDINGS / 'walkthrough_meta.json'}")

    if do_shots:
        print("capturing screenshots ...")
        capture_screenshots()


if __name__ == "__main__":
    main()
