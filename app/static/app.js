let lastData = { summary: { rows: 0 }, previews: [] };
let goldenData = { benchmarks: [], average_pct: 0 };
let currentSandboxPreview = null;
let presetsData = [];

const pages = document.querySelectorAll(".page");
const navItems = document.querySelectorAll(".nav-item");
const drawer = document.getElementById("drawer");
const drawerBackdrop = document.getElementById("drawerBackdrop");
const toast = document.getElementById("toast");

function showPage(name) {
  pages.forEach((page) => page.classList.toggle("active", page.id === `page-${name}`));
  navItems.forEach((btn) => btn.classList.toggle("active", btn.dataset.page === name));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

navItems.forEach((btn) => btn.addEventListener("click", () => showPage(btn.dataset.page)));

document.querySelector(".wordmark")?.addEventListener("click", (e) => {
  e.preventDefault();
  showPage("playground");
});

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3400);
}

function badgeClass(band) {
  if (band === "high") return "high";
  if (band === "review") return "review";
  return "low";
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function copyToClipboard(btn, text, label = "Text") {
  if (!navigator.clipboard) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  } else {
    navigator.clipboard.writeText(text);
  }

  if (btn) {
    const origText = btn.innerHTML;
    btn.classList.add("btn-copied");
    btn.innerHTML = "&#10004; Copied!";
    setTimeout(() => {
      btn.classList.remove("btn-copied");
      btn.innerHTML = origText;
    }, 2200);
  }
  showToast(`${label} copied to clipboard!`);
}

// ----------------------------------------------------
// 1. Golden Benchmarks & Operations Dashboard
// ----------------------------------------------------
function renderGolden() {
  const grid = document.getElementById("golden-grid");
  const avgEl = document.getElementById("golden-avg");
  const navEl = document.getElementById("nav-golden");
  if (!goldenData.benchmarks.length) {
    grid.innerHTML = '<div class="empty">Loading benchmarks…</div>';
    return;
  }
  const avgPct = `${goldenData.average_pct}%`;
  avgEl.textContent = avgPct;
  if (navEl) navEl.textContent = `${avgPct} golden`;

  grid.innerHTML = goldenData.benchmarks.map((item) => {
    return `
      <div class="golden-card">
        <div class="golden-pct">${item.score_pct}%</div>
        <div class="golden-mpn">${escapeHtml(item.mpn)}</div>
        <div class="golden-meta">${escapeHtml(item.brand || "Verified MFR")} · ${item.matches} / ${item.expected_filled} fields</div>
        <button class="btn btn-ghost btn-sm" onclick="inspectGoldenSKU('${escapeHtml(item.mpn)}')">Inspect</button>
      </div>
    `;
  }).join("");
}

function renderDashboard() {
  const summary = lastData.summary || { rows: 0 };
  const rowsEl = document.getElementById("stat-rows");
  if (rowsEl) rowsEl.textContent = summary.rows || 0;
  const filledEl = document.getElementById("stat-filled");
  if (filledEl) filledEl.textContent = summary.avg_filled_fields ? `${summary.avg_filled_fields}` : "—";
  const breakdown = summary.confidence_breakdown || {};
  const highEl = document.getElementById("stat-high");
  if (highEl) highEl.textContent = breakdown.high || 0;
  const issuesEl = document.getElementById("stat-issues");
  if (issuesEl) issuesEl.textContent = summary.rows_with_issues || 0;

  const lastOp = document.getElementById("last-op");
  if (!lastOp) return;
  if (!summary.rows) {
    lastOp.textContent = "";
    return;
  }
  const filterText = lastData.filter ? `Segment: ${lastData.filter}. ` : "";
  lastOp.textContent =
    `${filterText}${breakdown.high || 0} high-confidence, ${breakdown.review || 0} review-flagged.`;
}

// ----------------------------------------------------
// 2. Presets & SKU Sandbox (Interactive Playground)
// ----------------------------------------------------
async function loadPresets() {
  try {
    const res = await fetch("/api/presets");
    presetsData = await res.json();
    const container = document.getElementById("presets-list");
    container.innerHTML = presetsData.map((p, idx) => `
      <button class="preset-pill ${idx === 0 ? 'active' : ''}" data-idx="${idx}" type="button">
        <span>${escapeHtml(p.name)}</span>
        <span class="preset-cat-tag">${escapeHtml(p.badge)}</span>
      </button>
    `).join("");

    container.querySelectorAll(".preset-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        container.querySelectorAll(".preset-pill").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        applyPreset(Number(btn.dataset.idx));
      });
    });

    if (presetsData.length > 0) {
      applyPreset(0);
    }
  } catch (err) {
    console.error("Failed to load presets:", err);
  }
}

function applyPreset(idx) {
  const p = presetsData[idx];
  if (!p) return;
  document.getElementById("sb_mpn").value = p.Mfg_Part_Num || "";
  document.getElementById("sb_desc").value = p.Part_Desc || "";
  document.getElementById("sb_dib").value = p.DIB_Brand || "";
  document.getElementById("sb_e1").value = p.E1_Brand || "";
  document.getElementById("sb_unilog").value = p.Unilog_Brand || "";
  document.getElementById("sb_manuf").value = p.Part_Manuf || "";
}

async function runSandboxEnrichment(e) {
  if (e) e.preventDefault();
  const btn = document.getElementById("sbEnrichBtn");
  const container = document.getElementById("sb-result-container");

  btn.disabled = true;
  btn.textContent = "Enriching…";

  container.innerHTML = `
    <div class="skeleton skeleton-line short" style="height:22px;margin-bottom:0.75rem"></div>
    <div class="skeleton skeleton-line mid" style="height:14px"></div>
    <div class="skeleton skeleton-line" style="height:55px;margin-top:0.75rem"></div>
    <div class="skeleton skeleton-line" style="height:55px"></div>
    <div class="skeleton skeleton-line" style="height:90px"></div>
  `;

  const payload = {
    Mfg_Part_Num: document.getElementById("sb_mpn").value.trim(),
    Part_Desc: document.getElementById("sb_desc").value.trim(),
    DIB_Brand: document.getElementById("sb_dib").value.trim(),
    E1_Brand: document.getElementById("sb_e1").value.trim(),
    Unilog_Brand: document.getElementById("sb_unilog").value.trim(),
    Part_Manuf: document.getElementById("sb_manuf").value.trim(),
  };

  try {
    const res = await fetch("/api/enrich/single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    currentSandboxPreview = data.preview;
    renderSandboxOutput(data.preview);
    document.getElementById("sbOpenDrawerBtn").style.display = "inline-flex";
    document.getElementById("sb-status-sub").textContent = `${data.preview.filled_fields} / 252 fields · ${data.preview.completeness_pct}%`;
    showToast(`Enriched ${data.preview.mpn}`);
  } catch (err) {
    showToast("Enrichment error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Enrich";
  }
}

function renderSandboxOutput(p) {
  const container = document.getElementById("sb-result-container");
  const brand = p.identity.BRAND_NAME || p.identity.MANUFACTURER_NAME || "Verified MFR";
  const cat = p.taxonomy.Fine || p.taxonomy.Classpath || "Industrial Product";
  const specs = p.specs || [];
  const descs = p.descriptions_list || [];

  container.innerHTML = `
    <div class="result-head">
      <div>
        <div class="result-mpn">${escapeHtml(p.mpn)}</div>
        <div class="result-brand">${escapeHtml(brand)} · ${escapeHtml(cat)}</div>
      </div>
      <div class="result-figures">
        <span class="badge ${badgeClass(p.confidence_band)}">${p.confidence_band}</span>
        <span class="result-fields">${p.filled_fields} / 252 fields</span>
      </div>
    </div>

    <div class="microlabel" style="margin-bottom:0.4rem">Descriptions</div>
    <div class="desc-list">
      ${descs.slice(0, 3).map((d) => `
        <div class="desc-row">
          <span class="desc-row-label">${escapeHtml(d.title)}</span>
          <span class="desc-row-text">${escapeHtml(d.value)}</span>
          <span class="desc-row-meta">
            <span class="char-count ${d.valid ? '' : 'bad'}">${d.length}${d.max_len ? ' / ' + d.max_len : ''}</span>
            <button class="copy-btn" onclick="copyToClipboard(this, '${escapeHtml(d.value.replace(/'/g, "\\'"))}', '${escapeHtml(d.title)}')">Copy</button>
          </span>
        </div>
      `).join("")}
    </div>

    <div class="microlabel" style="margin-bottom:0.4rem">Attributes · ${specs.length} populated</div>
    <dl class="spec-rows">
      ${specs.slice(0, 8).map(s => `
        <div class="spec-row">
          <dt>${escapeHtml(s.label)}</dt>
          <dd>${escapeHtml(s.display)}</dd>
          <span class="source-tag">${escapeHtml(s.source)}</span>
        </div>
      `).join("")}
    </dl>
  `;
}

// ----------------------------------------------------
// 3. Catalog Explorer (PIM View)
// ----------------------------------------------------
function renderResults() {
  const body = document.getElementById("results-body");
  const filterText = document.getElementById("searchInput")?.value.toLowerCase() || "";
  const catFilter = document.getElementById("categoryFilter")?.value || "";
  const confFilter = document.getElementById("confidenceFilter")?.value || "";

  const previews = (lastData.previews || []).filter((row) => {
    if (catFilter && row.category_id !== catFilter) return false;
    if (confFilter && row.confidence_band !== confFilter) return false;
    if (!filterText) return true;
    const hay = `${row.mpn} ${row.identity.BRAND_NAME || ""} ${row.identity.MANUFACTURER_NAME || ""} ${row.taxonomy.Fine || ""} ${row.taxonomy.Classpath || ""} ${row.storefront_title || ""}`.toLowerCase();
    return hay.includes(filterText);
  });

  document.getElementById("gridCountLabel").textContent = `Showing ${previews.length} of ${(lastData.previews || []).length} products`;

  if (!previews.length) {
    body.innerHTML = `
      <tr><td colspan="7">
        <div class="empty">
          <h4>No matching records</h4>
          <p>Adjust the search or filters.</p>
        </div>
      </td></tr>`;
    return;
  }

  body.innerHTML = previews.map((row) => {
    const rawIdx = lastData.previews.indexOf(row);
    const cat = row.taxonomy.Fine || row.taxonomy.Classpath || "Generic Industrial";
    return `
      <tr data-index="${rawIdx}">
        <td>
          <div class="cell-mpn">${escapeHtml(row.mpn)}</div>
          <div class="cell-brand">${escapeHtml(row.identity.BRAND_NAME || row.identity.Part_Manuf || "—")}</div>
        </td>
        <td>${escapeHtml(row.identity.MANUFACTURER_NAME || row.identity.Part_Manuf || "—")}</td>
        <td class="cell-dim">${escapeHtml(cat)}</td>
        <td class="fields-cell">
          <div class="fields-line"><span>${row.filled_fields} / 252</span><span class="pct">${row.completeness_pct}%</span></div>
          <div class="mini-bar"><span style="width:${row.completeness_pct}%"></span></div>
        </td>
        <td class="cell-dim">${row.evidence_count}</td>
        <td><span class="conf-text ${row.confidence_band}">${row.confidence_band}</span></td>
        <td style="text-align:right">
          <button class="btn btn-secondary btn-xs" onclick="event.stopPropagation(); openDrawer(${rawIdx})">Inspect</button>
        </td>
      </tr>
    `;
  }).join("");

  body.querySelectorAll("tr[data-index]").forEach((tr) => {
    tr.addEventListener("click", () => openDrawer(Number(tr.dataset.index)));
  });
}

// ----------------------------------------------------
// 4. Complete 8-Tab Side Drawer Product Inspector
// ----------------------------------------------------
function openDrawer(index, customPreview = null) {
  const row = customPreview || lastData.previews[index];
  if (!row) return;

  document.getElementById("drawerMpn").textContent = row.mpn;
  const brand = row.identity.BRAND_NAME || row.identity.MANUFACTURER_NAME || "Manufacturer Direct";
  const cat = row.taxonomy.Fine || row.taxonomy.Classpath || "Industrial Commerce SKU";
  document.getElementById("drawerMeta").textContent = `${brand} • ${cat} • ${row.filled_fields} / 252 Fields (${row.completeness_pct}%)`;

  const confBadge = document.getElementById("drawerConfidenceBadge");
  confBadge.className = `badge ${badgeClass(row.confidence_band)}`;
  confBadge.textContent = row.confidence_band;

  // TAB 1: Diff View (Before vs After)
  document.getElementById("dtab-overview").innerHTML = `
    <div class="compare-grid">
      <div class="compare-col before">
        <h4>Sparse Distributor Input (6 Cols)</h4>
        ${Object.entries(row.input || {}).map(([k, v]) => `
          <div class="kv-row"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(v || "-")}</div></div>
        `).join("")}
      </div>
      <div class="compare-col after">
        <h4>Enriched 252-Col Delivery Highlights</h4>
        <div class="kv-row"><div class="k">Brand / Mfr</div><div class="v"><strong>${escapeHtml(brand)}</strong> / ${escapeHtml(row.identity.MANUFACTURER_NAME || "-")}</div></div>
        <div class="kv-row"><div class="k">Classpath</div><div class="v">${escapeHtml(row.taxonomy.Classpath || "-")}</div></div>
        <div class="kv-row"><div class="k">Density</div><div class="v"><strong>${row.filled_fields} / 252 headers</strong> (${row.completeness_pct}%)</div></div>
        <div class="kv-row"><div class="k">Evidence</div><div class="v">${row.evidence_count} manufacturer source citations</div></div>
        <div class="kv-row"><div class="k">Confidence</div><div class="v"><span class="badge ${badgeClass(row.confidence_band)}">${row.confidence_band}</span></div></div>
      </div>
    </div>
    ${renderStorefrontPDP(row)}
  `;

  // TAB 2: Structured Specifications & Attributes (50 Slots)
  const specs = row.specs || [];
  document.getElementById("dtab-specs").innerHTML = specs.length
    ? `
      <div class="specs-toolbar">
        <span class="specs-toolbar-title">${specs.length} of 50 attribute slots populated</span>
        <span class="microlabel">Standardized values & units</span>
      </div>
      <table class="specs-table">
        <thead>
          <tr>
            <th style="width:60px">Slot</th>
            <th>Attribute</th>
            <th>Value</th>
            <th>Unit</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          ${specs.map(s => `
            <tr>
              <td class="slot-num">#${s.slot}</td>
              <td style="font-weight:550">${escapeHtml(s.label)}</td>
              <td>${escapeHtml(s.value)}</td>
              <td class="attr-pill">${escapeHtml(s.uom || "—")}</td>
              <td><span class="source-tag">${escapeHtml(s.source)}</span></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `
    : '<div class="empty">No category attributes populated for this SKU.</div>';

  // TAB 3: 5x Descriptions
  const descs = row.descriptions_list || [];
  const features = row.features || [];
  document.getElementById("dtab-descriptions").innerHTML = descs.length
    ? `
      <div style="margin-bottom:1rem">
        ${descs.map(d => `
          <div class="desc-card">
            <div class="desc-card-head">
              <h4>${escapeHtml(d.title)}</h4>
              <div>
                <span class="desc-char-badge ${d.valid ? 'valid' : 'invalid'}">
                  ${d.length} ${d.max_len ? '/ ' + d.max_len : ''} chars ${d.valid ? '✓ Compliant' : '⚠ Non-compliant'}
                </span>
                <button class="btn btn-ghost btn-xs desc-copy-btn" onclick="copyToClipboard(this, '${escapeHtml(d.value.replace(/'/g, "\\'"))}', '${escapeHtml(d.title)}')">Copy</button>
              </div>
            </div>
            <div class="desc-card-body">${escapeHtml(d.value)}</div>
          </div>
        `).join("")}
      </div>
      ${features.length ? `
        <div class="drawer-subhead">Item features (${features.length})</div>
        <ul class="feature-list">
          ${features.map(f => `<li>${escapeHtml(f)}</li>`).join("")}
        </ul>
      ` : ''}
    `
    : '<div class="empty">No descriptions generated.</div>';

  // TAB 4: Storefront PDP Preview
  document.getElementById("dtab-storefront").innerHTML = renderStorefrontPDP(row);

  // TAB 5: Sources & URLs
  const sources = Object.entries(row.sources || {});
  document.getElementById("dtab-sources").innerHTML = sources.length
    ? `
      <div class="src-verified">
        <span class="compliance-icon">✓</span>
        <span>Sourced exclusively from official manufacturer and technical-document domains.</span>
      </div>
      ${sources.map(([k, v]) => `
        <div class="src-row">
          <div>
            <div class="src-k">${escapeHtml(k)}</div>
            <a class="src-url" href="${escapeHtml(v)}" target="_blank" rel="noopener">${escapeHtml(v)}</a>
          </div>
          <a class="btn btn-ghost btn-xs" href="${escapeHtml(v)}" target="_blank" rel="noopener">Open</a>
        </div>
      `).join("")}
    `
    : '<div class="empty">No source URLs captured.</div>';

  // TAB 6: Digital Assets
  const assets = row.assets || [];
  document.getElementById("dtab-assets").innerHTML = assets.length
    ? `
      <div class="asset-grid">
        ${assets.map(a => `
          <div class="asset-card">
            <div class="asset-type">${escapeHtml(a.title)}</div>
            <div class="asset-name">${escapeHtml(a.filename)}</div>
          </div>
        `).join("")}
      </div>
    `
    : '<div class="empty">No digital assets generated for this SKU.</div>';

  // TAB 7: Validation & Audit
  const issues = row.issues || [];
  document.getElementById("dtab-validation").innerHTML = `
    <div class="verdict ${issues.length ? 'warn' : 'good'}">
      <h4>${issues.length ? `${issues.length} validation finding${issues.length > 1 ? 's' : ''}` : 'Fully compliant'}</h4>
      <p>${issues.length ? 'Review the flagged items before publication.' : 'All list-of-values, unit and character-limit rules passed.'}</p>
    </div>
    ${issues.map(i => `<div class="issue">${escapeHtml(i)}</div>`).join("")}
  `;

  // TAB 8: Raw 252-Column Record
  const popFields = row.populated_fields || [];
  document.getElementById("dtab-raw").innerHTML = `
    <div class="specs-toolbar">
      <span class="specs-toolbar-title">${popFields.length} of 252 headers populated</span>
      <input type="search" class="raw-filter" placeholder="Filter headers…" oninput="filterRawHeaders(this.value)" />
    </div>
    <div style="max-height:480px;overflow-y:auto;">
      <table class="specs-table" id="rawHeadersTable">
        <thead>
          <tr>
            <th style="width:45%">Column</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          ${popFields.map(f => `
            <tr>
              <td class="cell-mpn" style="font-size:0.76rem">${escapeHtml(f.field)}</td>
              <td>${escapeHtml(f.value)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;

  setDrawerTab("overview");
  drawer.classList.add("open");
  drawerBackdrop.classList.add("open");
}

function filterRawHeaders(query) {
  const q = query.toLowerCase();
  document.querySelectorAll("#rawHeadersTable tbody tr").forEach(tr => {
    tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}

function renderStorefrontPDP(row) {
  const crumbs = [row.taxonomy.Dept, row.taxonomy.Class, row.taxonomy.Fine].filter(Boolean).join(" &rsaquo; ");
  const specs = (row.specs || []).slice(0, 8);
  const features = (row.features || []).slice(0, 6);
  const brand = row.identity.BRAND_NAME || row.identity.MANUFACTURER_NAME || "";

  return `
    <div class="storefront-mockup">
      <div class="store-header">
        <span>Storefront preview</span>
        <span class="store-badge">Commercial ready</span>
      </div>
      <div class="store-body">
        <div class="store-crumbs">${crumbs || "Industrial Products"}</div>
        <h1 class="store-h1">${escapeHtml(row.storefront_title)}</h1>
        <div class="store-pdp-meta">
          <span>MPN ${escapeHtml(row.mpn)}</span>
          · <span>${escapeHtml(brand)}</span>
          · <span>${escapeHtml(row.identity.MANUFACTURER_NAME || "—")}</span>
        </div>
        <div class="store-marketing">${escapeHtml(row.storefront_summary || row.long_desc || "Full commercial product data available.")}</div>
        ${features.length ? `
          <div class="drawer-subhead">Key features</div>
          <ul class="store-features-list">
            ${features.map(f => `<li>${escapeHtml(f)}</li>`).join("")}
          </ul>
        ` : ""}
        ${specs.length ? `
          <div class="drawer-subhead">Specifications</div>
          <table class="specs-table">
            <tbody>
              ${specs.map(s => `<tr><th style="width:40%">${escapeHtml(s.label)}</th><td>${escapeHtml(s.display)}</td></tr>`).join("")}
            </tbody>
          </table>
        ` : ""}
      </div>
    </div>
  `;
}

function closeDrawer() {
  drawer.classList.remove("open");
  drawerBackdrop.classList.remove("open");
}

function setDrawerTab(name) {
  document.querySelectorAll(".drawer-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.dtab === name);
  });
  document.querySelectorAll(".drawer-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `dtab-${name}`);
  });
}

document.getElementById("drawerClose").addEventListener("click", closeDrawer);
drawerBackdrop.addEventListener("click", closeDrawer);
document.querySelectorAll(".drawer-tab").forEach((btn) => {
  btn.addEventListener("click", () => setDrawerTab(btn.dataset.dtab));
});

// ----------------------------------------------------
// 5. Live Batch Pipeline (SSE Streamer)
// ----------------------------------------------------
function setPipelineStep(stepIndex) {
  document.querySelectorAll(".step-badge").forEach((el, index) => {
    el.classList.toggle("active", index === stepIndex);
    el.classList.toggle("done", index < stepIndex);
  });
}

function resetPipeline() {
  document.querySelectorAll(".step-badge").forEach((el) => {
    el.classList.remove("active", "done");
  });
}

function appendLog(tag, line) {
  const log = document.getElementById("progress-log");
  const timestamp = new Date().toISOString().substring(11, 19);
  log.textContent += `[${timestamp}] [${tag}] ${line}\n`;
  log.scrollTop = log.scrollHeight;
}

async function runLiveEnrichment() {
  const limit = document.getElementById("sampleLimit").value || "10";
  const filter = document.getElementById("sampleFilter").value;
  const btn = document.getElementById("liveBtn");
  const uploadBtn = document.getElementById("uploadBtn");
  const ticker = document.getElementById("active-sku-ticker");

  btn.disabled = true;
  uploadBtn.disabled = true;
  resetPipeline();
  setPipelineStep(0);
  document.getElementById("progress-message").textContent = "Initializing 8-stage deterministic pipeline...";
  document.getElementById("progress-fill").style.width = "0%";
  document.getElementById("progress-log").textContent = "";
  ticker.style.display = "flex";

  const phases = ["Ingest", "Resolve", "Classify", "Source", "Extract", "Normalize", "Compose", "Validate"];

  try {
    const res = await fetch(`/api/enrich/stream?limit=${encodeURIComponent(limit)}&filter=${encodeURIComponent(filter)}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk.split("\n").find((part) => part.startsWith("data: "));
        if (!line) continue;
        const payload = JSON.parse(line.slice(6));

        if (payload.type === "start") {
          appendLog("START", `Batch initialized for ${payload.total} distributor SKUs`);
          setPipelineStep(0);
        }

        if (payload.type === "step") {
          const stepIndex = Math.min(7, Math.floor(((payload.current - 1) % 8)));
          setPipelineStep(stepIndex);
          document.getElementById("progress-message").textContent = `${phases[stepIndex]}: Processing ${payload.mpn}`;
          ticker.innerHTML = `
            <span><strong>Processing:</strong> ${escapeHtml(payload.mpn)} (${payload.current} / ${payload.total})</span>
            <span class="preset-cat-tag">Phase: ${phases[stepIndex]}</span>
          `;
          const pct = Math.round(((payload.current - 0.5) / payload.total) * 100);
          document.getElementById("progress-fill").style.width = `${pct}%`;
        }

        if (payload.type === "row") {
          appendLog("ENRICHED", `${payload.mpn} -> ${payload.brand || "MFR"} | ${payload.category || "Classified"} (${payload.filled} fields, ${payload.confidence})`);
          const pct = Math.round((payload.current / payload.total) * 100);
          document.getElementById("progress-fill").style.width = `${pct}%`;
        }

        if (payload.type === "complete") {
          setPipelineStep(7);
          document.querySelectorAll(".step-badge").forEach((el) => el.classList.add("done"));
          document.getElementById("progress-fill").style.width = "100%";
          document.getElementById("progress-message").textContent = `Complete: ${payload.rows} SKUs enriched into 252-column delivery format.`;
          ticker.innerHTML = `<span><strong>Batch Completed:</strong> ${payload.rows} SKUs successfully processed</span><span class="badge high">100% Verified</span>`;
          appendLog("SUCCESS", `Saved delivery output to upload_output.csv, enriched.xlsx & field_provenance.json`);

          lastData = {
            filter: payload.filter,
            summary: payload.summary,
            previews: payload.previews,
            rows: payload.rows,
          };
          renderDashboard();
          renderResults();
          showToast(`Enriched ${payload.rows} products successfully`);
          showPage("results");
        }
      }
    }
  } catch (err) {
    document.getElementById("progress-message").textContent = `Error: ${err.message}`;
    appendLog("ERROR", err.message);
    showToast("Enrichment stream interrupted");
  } finally {
    btn.disabled = false;
    uploadBtn.disabled = false;
  }
}

async function runUpload() {
  const fileInput = document.getElementById("file");
  if (!fileInput.files.length) {
    showToast("Please choose a CSV file to upload");
    return;
  }
  const uploadBtn = document.getElementById("uploadBtn");
  uploadBtn.disabled = true;
  document.getElementById("progress-message").textContent = "Uploading & processing batch...";
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  form.append("limit", document.getElementById("limit").value || "0");

  try {
    const res = await fetch("/enrich", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    lastData = data;
    renderDashboard();
    renderResults();
    showToast(`Uploaded & enriched ${data.rows} products!`);
    showPage("results");
  } catch (err) {
    showToast("Upload error: " + err.message);
  } finally {
    uploadBtn.disabled = false;
  }
}

// ----------------------------------------------------
// 6. Taxonomy & LOV Directory
// ----------------------------------------------------
async function loadTaxonomy() {
  try {
    const res = await fetch("/api/taxonomy");
    const data = await res.json();
    const container = document.getElementById("taxonomy-templates-list");
    document.getElementById("templateCountSub").textContent = `${data.template_count} Category Templates • ${data.leaf_count} Indexed Leaf Nodes`;

    container.innerHTML = (data.templates || []).map(t => `
      <div class="template-card">
        <strong>${escapeHtml(t.product_name || t.fine)}</strong>
        <small>${escapeHtml(t.classpath)}</small>
        <span class="attr-pill">${t.attribute_count} Category Attributes</span>
      </div>
    `).join("");
  } catch (err) {
    console.error("Failed to load taxonomy:", err);
  }
}

function inspectGoldenSKU(mpn) {
  const foundIdx = (lastData.previews || []).findIndex(p => p.mpn === mpn);
  if (foundIdx >= 0) {
    openDrawer(foundIdx);
  } else {
    const presetIdx = presetsData.findIndex(p => p.Mfg_Part_Num === mpn);
    if (presetIdx >= 0) {
      applyPreset(presetIdx);
      showPage("playground");
      runSandboxEnrichment();
    }
  }
}

// ----------------------------------------------------
// Initial Load & Event Listeners
// ----------------------------------------------------
async function loadGolden() {
  try {
    const res = await fetch("/api/golden");
    goldenData = await res.json();
    renderGolden();
  } catch (_) {
    document.getElementById("golden-grid").innerHTML = '<div class="empty">Could not load golden benchmarks.</div>';
  }
}

async function loadLastRun() {
  const res = await fetch("/api/last-run");
  if (!res.ok) return;
  const data = await res.json();
  if (data.summary && data.summary.rows) {
    lastData = data;
    renderDashboard();
    renderResults();
  }
}

document.getElementById("playgroundForm")?.addEventListener("submit", runSandboxEnrichment);
document.getElementById("playgroundResetBtn")?.addEventListener("click", () => {
  document.getElementById("playgroundForm").reset();
  document.getElementById("sb-result-container").innerHTML = `
    <div class="wb-empty">
      <p>Run an enrichment to see the complete record.</p>
    </div>
  `;
  document.getElementById("sbOpenDrawerBtn").style.display = "none";
});

document.getElementById("sbOpenDrawerBtn")?.addEventListener("click", () => {
  if (currentSandboxPreview) openDrawer(-1, currentSandboxPreview);
});

document.getElementById("liveBtn")?.addEventListener("click", runLiveEnrichment);
document.getElementById("uploadBtn")?.addEventListener("click", runUpload);
document.getElementById("refreshBtn")?.addEventListener("click", loadLastRun);
document.getElementById("refreshGoldenBtn")?.addEventListener("click", loadGolden);
document.getElementById("quickDemoBtn")?.addEventListener("click", () => {
  showPage("playground");
  applyPreset(0);
  runSandboxEnrichment();
});

document.getElementById("searchInput")?.addEventListener("input", renderResults);
document.getElementById("categoryFilter")?.addEventListener("change", renderResults);
document.getElementById("confidenceFilter")?.addEventListener("change", renderResults);
document.getElementById("clearLogBtn")?.addEventListener("click", () => {
  document.getElementById("progress-log").textContent = "";
});

// Bootstrap
loadPresets();
loadGolden();
loadLastRun();
loadTaxonomy();
