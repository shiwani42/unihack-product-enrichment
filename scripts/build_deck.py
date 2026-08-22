#!/usr/bin/env python3
"""Fill the official UniHack prototype template with the thExplorers submission.

Usage: PYTHONPATH=. python3 scripts/build_deck.py
Reads guidelines/[EXT] UniHack-Protoype Template .pptx and writes
submission/UniHack_thExplorers_Prototype.pptx. Screenshots come from
demo_build/screenshots/. Idempotent: always rebuilds from the pristine template.
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "guidelines" / "[EXT] UniHack-Protoype Template .pptx"
SHOTS = ROOT / "demo_build" / "screenshots"
OUT = ROOT / "submission" / "UniHack_thExplorers_Prototype.pptx"

INK = RGBColor(0x0D, 0x0D, 0x0F)
MUTED = RGBColor(0x55, 0x55, 0x5C)
GREEN = RGBColor(0x06, 0x76, 0x47)
HAIR = RGBColor(0xE8, 0xE8, 0xED)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SANS = "Segoe UI"
MONO = "Consolas"

GITHUB = "https://github.com/shiwani42/unihack-product-enrichment"


def box(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    return tb, tf


def style(par, text, size=12, bold=False, color=INK, font=SANS, align=None,
          space_after=4, bullet=False):
    par.text = ("\u2022  " + text) if bullet else text
    if align is not None:
        par.alignment = align
    par.space_after = Pt(space_after)
    for run in par.runs:
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = font
    return par


def line(tf, text, **kw):
    return style(tf.add_paragraph(), text, **kw)


def fill_tf(tf, items):
    """items: list of (text, kwargs)."""
    first = True
    for text, kw in items:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        style(p, text, **kw)


def card(slide, x, y, w, h, fill=WHITE, border=HAIR):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                                Inches(w), Inches(h))
    sh.adjustments[0] = 0.06
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = border
    sh.line.width = Pt(1)
    sh.shadow.inherit = False
    return sh


def arrow(slide, x, y, w=Inches(0.28)):
    ar = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x, y, w, Inches(0.22))
    ar.fill.solid()
    ar.fill.fore_color.rgb = MUTED
    ar.line.fill.background()
    ar.shadow.inherit = False
    return ar


def shot(slide, path, x, y, w, caption=None):
    img = slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w))
    if caption:
        _, tf = box(slide, x, y + img.height / 914400 + 0.03, w, 0.3)
        fill_tf(tf, [(caption, dict(size=9, color=MUTED))])
    fr = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x - 0.01),
                                Inches(y - 0.01),
                                Emu(int(img.width) + 18288),
                                Emu(int(img.height) + 18288))
    fr.fill.background()
    fr.line.color.rgb = HAIR
    fr.shadow.inherit = False
    slide.shapes._spTree.remove(fr._element)
    slide.shapes._spTree.insert(list(slide.shapes._spTree).index(img._element), fr._element)
    return img


def main() -> None:
    prs = Presentation(str(TEMPLATE))
    slides = list(prs.slides)

    def wipe(slide, keep_ids=()):
        for shape in list(slide.shapes):
            if shape.has_text_frame and shape.shape_id not in keep_ids:
                slide.shapes._spTree.remove(shape._element)

    # ---- S1 title ----
    s = slides[0]
    wipe(s)
    _, tf = box(s, 0.7, 1.55, 8.6, 2.4)
    fill_tf(tf, [
        ("unilog enrichment engine", dict(size=40, bold=True)),
        ("Evidence-first product intelligence for industrial commerce",
         dict(size=18, color=MUTED)),
        ("Six columns in. 252 out. Every value traceable to its source.",
         dict(size=14, color=GREEN, bold=True)),
    ])
    _, tf = box(s, 0.7, 4.35, 8.6, 0.6)
    fill_tf(tf, [("Team thExplorers \u00b7 Shiwani Mishra \u00b7 Saurabh Gupta \u00b7 UniHack 2026",
                  dict(size=12, color=MUTED))])

    # ---- S2 team ----
    s = slides[1]
    _, tf = box(s, 0.4, 2.6, 9.2, 1.6)
    fill_tf(tf, [
        ("Team name:  thExplorers", dict(size=16)),
        ("Team leader name:  Shiwani Mishra", dict(size=16)),
        ("Member:  Saurabh Gupta", dict(size=16)),
    ])

    # ---- S3 brief ----
    s = slides[2]
    _, tf = box(s, 0.45, 1.75, 9.1, 3.5)
    fill_tf(tf, [
        ("Distributors hand us six columns: a part number, a cryptic description and "
         "brand placeholders. We hand back a commerce-ready record in Unilog's 252-column "
         "delivery format.", dict(size=15, bold=True)),
        ("How: manufacturer-first sourcing (\u2265 Amazon/eBay blocked) \u2192 identity resolution "
         "(brand aliases, MPN prefix rules) \u2192 leaf-level classification \u2192 category attribute "
         "slots \u2192 HTML/PDF evidence extraction \u2192 normalisation \u2192 five description types "
         "\u2192 validation.", dict(size=13), ),
        ("Deterministic rules do the heavy lifting; an LLM only handles the last mile for "
         "cryptic rows \u2014 and blank beats invented. Every populated value carries a source URL "
         "and a confidence band.", dict(size=13)),
    ])
    stats = [("100%", "field match vs organizer\nexpected output (134/134)"),
             ("1000/1000", "input rows classified,\nzero unroutable"),
             ("77", "hermetic tests,\n~2s suite"),
             ("$0.0004", "compute cost per SKU\n(rules path)")]
    for i, (big, small) in enumerate(stats):
        x = 0.45 + i * 2.33
        c = card(s, x, 4.05, 2.13, 1.05)
        tf = c.text_frame
        tf.word_wrap = True
        fill_tf(tf, [(big, dict(size=20, bold=True, color=GREEN, align=PP_ALIGN.CENTER)),
                     (small, dict(size=9, color=MUTED, align=PP_ALIGN.CENTER))])

    # ---- S4 three questions ----
    s = slides[3]
    ph = next(sh for sh in s.shapes if sh.is_placeholder)
    tf = ph.text_frame
    tf.clear()
    qa = [
        ("1. How does your solution enrich minimal product information?",
         dict(size=12, bold=True, space_after=2)),
        ("Input analysis \u2192 de-duplication \u2192 identity (brand aliases, MPN-prefix rules) \u2192 "
         "leaf-level routing into 13 category templates \u2192 manufacturer-site extraction "
         "(HTML specs, JSON-LD, PDF datasheets) \u2192 unit/LOV normalisation \u2192 five governed "
         "descriptions \u2192 validated 252-column delivery row.", dict(size=11, space_after=8)),
        ("2. How does your solution ensure accuracy and trust?",
         dict(size=12, bold=True, space_after=2)),
        ("Golden regression vs the organizer's expected output: 100% on both reference SKUs "
         "(134/134 fields). Per-value provenance JSON (source URL per cell). Honest confidence "
         "bands \u2014 \u201chigh\u201d requires externally verified manufacturer evidence; self-cited values "
         "are capped at medium/review. Validators enforce LOV membership, character limits, UOM "
         "style and attribute sanity. Integrity tests ban fabricated defaults: blank beats "
         "invented.", dict(size=11, space_after=8)),
        ("3. What makes your solution scalable for enterprise catalogs?",
         dict(size=12, bold=True, space_after=2)),
        ("Stateless row pipeline \u2192 parallel workers with dedup merge, not drop. Cache-first "
         "fetching under a hard per-run network budget; atomic cache writes; retry/backoff. "
         "Streaming SSE API for live ops plus CLI batch for millions of rows. Adding a category "
         "= one JSON template, no code. 1,000-row sample runs offline-deterministic in ~60s.",
         dict(size=11)),
    ]
    fill_tf(tf, qa)

    # ---- S5 opportunities ----
    s = slides[4]
    _, tf = box(s, 0.4, 1.85, 9.2, 3.4)
    fill_tf(tf, [
        ("Different from existing ideas", dict(size=14, bold=True, space_after=2)),
        ("Enrichment tools stop at filling fields. Ours makes every filled cell auditable: a "
         "provenance drawer exposes the exact source URL behind each attribute, and confidence "
         "bands say which values a buyer can trust without re-checking.", dict(size=12,
                                                                               space_after=8)),
        ("USP", dict(size=14, bold=True, space_after=2)),
        ("Audit-proof enrichment: \u201cevery value verifiable in one click.\u201d Accuracy is measured, "
         "not claimed \u2014 scored field-by-field against the organizer's own expected output.",
         dict(size=12, space_after=8)),
        ("Fit to the problem statement", dict(size=14, bold=True, space_after=2)),
        ("Manual involvement drops from research-per-SKU to review-by-exception: rows that lack "
         "manufacturer evidence are flagged for human review instead of being silently guessed. "
         "That is exactly the trust bar a 100%-accuracy target demands.", dict(size=12)),
    ])

    # ---- S6 features ----
    s = slides[5]
    feats_l = [
        "6-column input \u2192 252-column delivery CSV/XLSX, headers untouched",
        "Manufacturer-first sourcing; marketplace blocklist (Amazon/eBay\u2026)",
        "Leaf-level classification: 13 templates + generic industrial fallback",
        "Category attribute slots filled only when evidence exists",
        "Per-value provenance: source URL for every populated cell",
        "Five description types within char limits (invoice/mobile/short/long/retail)",
    ]
    feats_r = [
        "Marketing copy & item features only from manufacturer pages",
        "Digital assets named per delivery convention; honest Actual Image flag",
        "Validation suite: LOV, char limits, UOM style, ecommerce block, sanity",
        "Confidence bands: high/medium/review, evidence-gated",
        "Live ops: SSE stream UI, catalog grid, SKU drawer, storefront preview",
        "Golden regression harness + 77 hermetic tests guard every change",
    ]
    _, tf = box(s, 0.4, 1.8, 4.55, 3.5)
    fill_tf(tf, [(t, dict(size=11.5, space_after=6, bullet=True)) for t in feats_l])
    _, tf = box(s, 5.1, 1.8, 4.55, 3.5)
    fill_tf(tf, [(t, dict(size=11.5, space_after=6, bullet=True)) for t in feats_r])

    # ---- S7 process flow ----
    s = slides[6]
    stages = [
        ("1. Input analysis", "6 cols, placeholders,\ndupes detected"),
        ("2. Identity", "brand aliases,\nMPN prefix rules"),
        ("3. Classification", "leaf-level routing,\n13 templates"),
        ("4. Extraction", "HTML \u00b7 JSON-LD \u00b7\nPDF \u00b7 cache-first"),
        ("5. Normalisation", "units \u00b7 LOV \u00b7\ncanonical brands"),
        ("6. Descriptions", "5 governed types,\nchar limits"),
        ("7. Validation", "rules \u00b7 confidence\nbands \u00b7 issues"),
        ("8. Delivery", "CSV/XLSX +\nprovenance JSON"),
    ]
    x0, y0 = 0.42, 2.15
    cw, ch = 2.0, 1.06
    step = 2.34
    for i, (title, sub) in enumerate(stages):
        r, c = divmod(i, 4)
        x = x0 + c * step
        y = y0 + r * (ch + 0.62)
        cshape = card(s, x, y, cw, ch)
        tfc = cshape.text_frame
        tfc.word_wrap = True
        fill_tf(tfc, [
            (title, dict(size=12, bold=True, color=GREEN if i in (0, 7) else INK,
                         space_after=1)),
            (sub, dict(size=9, color=MUTED)),
        ])
        if c < 3:
            arrow(s, Emu(Inches(x + cw + 0.04)), Emu(Inches(y + ch / 2 - 0.11)))
    ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x0), Inches(y0 + 2 * ch + 0.66),
                            Inches(9.2), Pt(1))
    ln.fill.solid(); ln.fill.fore_color.rgb = HAIR; ln.line.fill.background()
    _, tf = box(s, x0, y0 + 2 * ch + 0.72, 9.2, 0.35)
    fill_tf(tf, [("Fail-safe: every row wrapped in try/except \u2014 a bad row never kills the batch.",
                  dict(size=10, color=MUTED))])

    # ---- S8 wireframes ----
    s = slides[7]
    shot(s, SHOTS / "hero.png", 0.45, 1.75, 4.35, "Enrich workbench \u2014 default view")
    shot(s, SHOTS / "enrich_result.png", 5.15, 1.75, 4.35, "Result panel \u2014 spec-sheet record")

    # ---- S9 architecture ----
    s = slides[8]
    layers = [
        ("Interface", "FastAPI \u00b7 SSE stream \u00b7 static web UI \u00b7 CLI"),
        ("Orchestration", "pipeline.enrich_input_row \u2014 fail-safe per row \u00b7 dedup merge \u00b7 parallel workers"),
        ("Intelligence", "identity/ brand resolver \u00b7 classify/ router + templates \u00b7 extract/ HTML-PDF-JSON-LD \u00b7 optional LLM last-mile"),
        ("Trust", "validate/ LOV + limits + sanity \u00b7 provenance map \u00b7 confidence bands \u00b7 golden harness"),
        ("Delivery", "CSV \u00b7 XLSX \u00b7 provenance JSON \u00b7 batch reports"),
    ]
    y = 1.8
    for i, (name, tech) in enumerate(layers):
        cshape = card(s, 0.7, y, 8.6, 0.62)
        tf = cshape.text_frame
        fill_tf(tf, [(f"{name}   \u2014   {tech}",
                      dict(size=11.5, bold=(i == 0)))])
        y += 0.78
    _, tf = box(s, 0.7, y + 0.02, 8.6, 0.5)
    fill_tf(tf, [("Uniform cache-first fetch policy: retry/backoff, atomic writes, raw-cache TTL, "
                  "per-run budget (UNILOG_FETCH_BUDGET). Optional Playwright fallback on 403.",
                  dict(size=10, color=MUTED))])

    # ---- S10 technologies ----
    s = slides[9]
    techs = [
        ("Python 3.11", "pipeline core, fully typed modules"),
        ("FastAPI + SSE", "upload, live stream, downloads"),
        ("httpx + Playwright", "resilient fetching, 403 fallback"),
        ("BeautifulSoup + extruct", "HTML tables, JSON-LD, microdata"),
        ("pdfplumber", "manufacturer PDF datasheets"),
        ("openpyxl", "delivery-format XLSX"),
        ("pytest \u00d7 77", "hermetic suite, offline by default"),
        ("Remotion + FFmpeg", "reproducible demo film build"),
    ]
    for i, (name, why) in enumerate(techs):
        r, c = divmod(i, 2)
        x = 0.5 + c * 4.65
        yy = 1.85 + r * 0.82
        cshape = card(s, x, yy, 4.4, 0.68)
        fill_tf(cshape.text_frame, [
            (name, dict(size=13, bold=True, font=MONO, space_after=0)),
            (why, dict(size=9.5, color=MUTED)),
        ])
    _, tf = box(s, 0.5, 5.0, 9.0, 0.4)
    fill_tf(tf, [("Optional LLM fallback (gpt-4o-mini, hard-capped calls) only for cryptic rows "
                  "with unknown brand \u2014 off by default.", dict(size=10, color=MUTED))])

    # ---- S11 cost ----
    s = slides[10]
    rows = [
        ("Approach", "Cost per SKU", "Notes"),
        ("Manual enrichment (offshore)", "$5.00\u2013$15.00", "industry rate for research + entry"),
        ("unilog \u2014 rules path", "$0.0004", "CPU only; 1,000 rows \u2248 60s, zero API calls"),
        ("unilog \u2014 LLM last-mile (worst case)", "$0.0204 max", "hard-capped calls/run; off by default"),
    ]
    y = 2.0
    for i, (a, b, c) in enumerate(rows):
        head = i == 0
        cshape = card(s, 0.7, y, 8.6, 0.6, fill=HAIR if head else WHITE)
        fill_tf(cshape.text_frame, [("", dict(size=1))])
        _, tfa = box(s, 0.95, y + 0.12, 3.6, 0.4)
        style(tfa.paragraphs[0], a, size=12, bold=head)
        _, tfb = box(s, 4.7, y + 0.12, 1.7, 0.4)
        style(tfb.paragraphs[0], b, size=12, bold=True,
              color=GREEN if not head else INK, font=MONO)
        _, tfc = box(s, 6.5, y + 0.12, 2.7, 0.4)
        style(tfc.paragraphs[0], c, size=9.5, color=MUTED)
        y += 0.72
    _, tf = box(s, 0.7, y + 0.1, 8.6, 0.6)
    fill_tf(tf, [("A 1M-SKU catalog: ~$400 compute on the rules path vs $5M\u201315M manually \u2014 four "
                  "orders of magnitude, with provenance humans can audit.", dict(size=12,
                                                                                 bold=True))])

    # ---- S12 MVP snapshots (aspect-aware grid, no overlaps) ----
    s = slides[11]
    from PIL import Image

    def place(path, x, y, w, caption=None):
        with Image.open(path) as im:
            ar = im.height / im.width
        h = w * ar
        shot(s, path, x, y, w, caption)
        return h

    h1 = place(SHOTS / "proof_band.png", 0.7, 1.62, 4.0, "Golden accuracy \u2014 verified on home")
    place(SHOTS / "catalog_table.png", 5.3, 1.62, 4.0, "Catalog \u2014 enriched results")
    y2 = 1.62 + max(h1, 2.45) + 0.18
    bw = min(2.9, (5.5 - y2) / 0.5625)
    place(SHOTS / "drawer_evidence.png", 2.0, y2, bw)
    place(SHOTS / "catalog_export.png", 5.4, y2, bw)

    # ---- S13 future ----
    s = slides[12]
    fut = [
        ("Organizer reference packs", "drop-in importer already ships: real LOV (~161k rows), UOM standards, 27k brand list, 200-row ground-truth scorer activate automatically."),
        ("Taxonomy at 14k scale", "embedding-based matcher over the full leaf index alongside current rule router."),
        ("Human review queue", "review-band rows land in a triage UI; approvers publish to CX1-style PIM."),
        ("HyperScale agent fit", "packaged as a Merchandising-Agent accelerator: same provenance contract, streaming connector for distributor ERPs."),
    ]
    _, tf = box(s, 0.5, 1.8, 9.0, 3.4)
    items = []
    for name, desc in fut:
        items.append((name, dict(size=13, bold=True, space_after=1)))
        items.append((desc, dict(size=11.5, space_after=8)))
    fill_tf(tf, items)

    # ---- S14 links ----
    s = slides[13]
    wipe(s)
    links = [
        ("GitHub Public Repository", GITHUB),
        ("Demo Video Link (3 Minutes)", "https://vimeo.com/1220615209"),
        ("Working Prototype Link", "https://unilog-tau.vercel.app"),
    ]
    y = 2.1
    for label, url in links:
        _, tf = box(s, 0.7, y, 8.8, 0.75)
        fill_tf(tf, [(label, dict(size=13, bold=True, space_after=0)),
                     (url, dict(size=12, font=MONO, color=GREEN))])
        y += 1.05

    # ---- S15 closing ----
    s = slides[14]
    _, tf = box(s, 0.7, 2.3, 8.6, 1.0)
    fill_tf(tf, [
        ("Thank you", dict(size=30, bold=True)),
        ("thExplorers \u00b7 UniHack 2026", dict(size=13, color=MUTED)),
    ])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
