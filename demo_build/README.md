# unilog — 3-minute hackathon demo film

Canonical output: `demo.mp4` — 1920x1080, 30 fps, H.264 + yuv420p (BT.709, tv
range), AAC 48 kHz stereo, **178.048 s** (5340 frames), 37.2 MB.

Story: when a distributor pastes one cryptic part line, unilog resolves the
manufacturer, classifies it, fills commerce attributes with per-value source
URLs, and exports a delivery-ready 252-column record — proven, not promised.

## Scenes (30 fps, 18-frame fades between)

| # | id | frames | content |
|---|----|--------|---------|
| S1 | cold-open | 520 | dark card: "Distributors hand you six columns." + cryptic row `DCB518ASTS06G — Diablo 1/2x18 Sanding Belt` |
| S2 | mechanism | 690 | 5 pipeline cards; "Rules first. LLM only for the last mile. Blank beats invented." |
| S3 | live-proof | 2700 | recorded walkthrough in a browser frame with slow zooms + captions: intro → live enrich → provenance drawer → batch stream → golden 100% → export |
| S4 | trust | 842 | stat cards: 134/134 fields vs organizer expected output (2 reference SKUs), 1000/1000 rows classified, 77 hermetic tests, high-confidence evidence rule |
| S5 | close | 660 | unilog wordmark, tagline, GitHub URL, thExplorers; final frame holds ~3 s |

Total = 5412 scene frames − 4×18 transition overlap = 5340 frames = 178.00 s.

## Real evidence

- `recordings/walkthrough.mp4` — one continuous 1920x1080 30 fps CFR Playwright
  recording (110.633 s, h264/yuv420p, 3319 frames) of the real app at
  http://localhost:8000: hero load → type MPN/brand/description → Enrich →
  Catalog row → drawer → Sources tab → Batch run to completion (1000 rows) →
  Quality → Export CSV download. Validated by `scripts/validate_recording.py`
  and re-validated inside `tests/storyboard.test.ts` via ffprobe.
- `screenshots/*.png` — six 1920x1080 stills of the same live app (hero,
  enrich result, catalog table, drawer sources, quality 100%, export page).
  `export_page.png` is a sparse white page and is legitimately <80 KB; all
  stills were visually inspected at full resolution.

The walkthrough was captured once (see `capture_walkthrough.py` +
`interaction_plan.json`; `recordings/walkthrough_meta.json` is the
authoritative segment/action log) and is trimmed into named proof segments in
`src/storyboard.ts` rather than re-recorded.

## Setup

```bash
cd demo_build
npm install            # remotion + @remotion/* pinned to 4.0.515
# the product itself must be running:
cd .. && PYTHONPATH=. UNILOG_LIVE_FETCH=0 python3 -m uvicorn app.main:app --port 8000 &
```

## Refresh live captures (optional; existing verified captures are reused)

```bash
npm run capture        # python3 capture_walkthrough.py → recordings/
npm run assets         # validates captures, copies into public/, fetches fonts, generates score
```

`npm run assets` runs `scripts/validate_recording.py` (exact codec/dims/fps/
frame-count) and `scripts/validate_screenshots.py`, copies canonical assets
into `public/`, downloads Inter + JetBrains Mono woff2 into `public/fonts/`
(`scripts/fetch_fonts.py`, offline after first run) and renders the
deterministic ambient score (`scripts/generate_score.py`, 178.5 s @ 96 BPM).

## Preview

```bash
npm run dev            # Remotion Studio at :3000
```

## Tests / checks

```bash
npm run test           # vitest: storyboard + interaction-plan contracts (12 tests)
npm run lint           # tsc --noEmit
npm run compositions   # composition discovery gate (Demo 5340 frames)
npm run check          # all three
```

Contracts covered: scene order/durations, total = 5340 frames in [175, 180] s,
proof-segment math, required assets exist, source recording is exact-frame
1920x1080 30 fps h264 (ffprobe), actions ordered/unique/in-bounds, full
product path walked, declared segments contiguous across the recording.

## Render

```bash
npm run render         # assets → remotion render → finalize
```

`finalize` re-muxes with `-pix_fmt yuv420p -color_range tv -colorspace bt709`
because Remotion's JPEG image format emits full-range `yuvj420p`.

## Verify the artifact

```bash
ffprobe -v error -show_entries format=duration,size,bit_rate:stream=codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,pix_fmt,sample_rate,channels -of default=noprint_wrappers=1 demo.mp4
ffmpeg -hide_banner -i demo.mp4 -map 0:a:0 -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
ffmpeg -v error -i demo.mp4 -vf "fps=1/7.7,scale=480:-1,tile=4x6" -frames:v 1 contact_sheet_final.png
```

Last verified output (2026-08-23):

- video: h264, yuv420p, 1920x1080, r_frame_rate 30/1, avg 30/1, 5340 frames
- audio: aac, 48000 Hz, 2 channels (score mean −26.0 dB, peak −12.4 dB — no clipping)
- duration 178.048 s, size 37,202,624 bytes, overall bit_rate 1.67 Mb/s

Two-pass process: 23 representative stills (`stills/`) tiled into
`contact_sheet_stills.png` and inspected before the full render; the encoded
MP4 was then tiled into `contact_sheet_final.png` and inspected again —
headlines ≥84 px, captions ≥34 px, safe margins respected, final frame stable.

## Notes

- Fonts are bundled locally for offline-reproducible renders.
- Remotion license: company size determines license requirements; see
  https://www.remotion.dev/license for the team's terms.
- `public/` is generated (ignored); canonical evidence lives in
  `recordings/` and `screenshots/`.
