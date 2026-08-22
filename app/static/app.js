const TOTAL_COLUMNS = 252;

let lastData = { summary: { rows: 0 }, previews: [] };
let presetsData = [];
let taxonomyTemplates = [];
let currentSandboxPreview = null;

const copyRegistry = new Map();
let copySeq = 0;

let ignoreHashChange = false;
let drawerReturnHash = "#/catalog";
let lastFocusedElement = null;

function el(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function showToast(message, isError = false) {
  const toast = el("toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), isError ? 4200 : 2600);
}

function badgeClass(band) {
  if (band === "high") return "high";
  if (band === "review") return "review";
  return "low";
}

// ---------- Router ----------

const PAGES = ["enrich", "catalog"];

function parseHash(hash) {
  const h = (hash || "").replace(/^#\/?/, "");
  if (!h) return { page: "enrich" };
  const [head, rest] = h.split("/");
  if (PAGES.includes(head)) return { page: head };
  if (head === "record") return { page: "catalog", record: decodeURIComponent(rest || "") };
  return { page: "enrich" };
}

function setHash(hash) {
  if (location.hash === hash) return;
  ignoreHashChange = true;
  location.hash = hash;
}

function go(hash) {
  setHash(hash);
  route();
}

function route() {
  const { page, record } = parseHash(location.hash);
  showPage(page);
  if (record) {
    const row = (lastData.previews || []).find((p) => p.mpn === record);
    if (row) openDrawer(row, { silent: true });
    else go("#/catalog");
  } else {
    hideDrawer();
  }
}

window.addEventListener("hashchange", () => {
  if (ignoreHashChange) {
    ignoreHashChange = false;
    return;
  }
  route();
});

function showPage(name) {
  document.querySelectorAll(".page").forEach((page) =>
    page.classList.toggle("active", page.id === `page-${name}`)
  );
  document.querySelectorAll(".nav-item").forEach((btn) => {
    const active = btn.dataset.page === name;
    btn.classList.toggle("active", active);
    if (active) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  window.scrollTo(0, 0);
}

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => go(`#/${btn.dataset.page}`));
});

// ---------- Copy (registry-based, no inline handlers) ----------

function regCopy(text) {
  const key = `k${++copySeq}`;
  copyRegistry.set(key, String(text ?? ""));
  return key;
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-copy-key]");
  if (!btn) return;
  const text = copyRegistry.get(btn.dataset.copyKey);
  if (text == null) return;

  if (navigator.clipboard) {
    navigator.clipboard.writeText(text);
  } else {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }

  const original = btn.textContent;
  btn.classList.add("btn-copied");
  btn.textContent = "Copied";
  setTimeout(() => {
    btn.classList.remove("btn-copied");
    btn.textContent = original;
  }, 1600);
});

// ---------- Dashboard ----------

function renderDashboard() {
  const summary = lastData.summary || {};
  const breakdown = summary.confidence_breakdown || {};
  el("stat-rows").textContent = summary.rows || 0;
  el("stat-filled").textContent = summary.avg_filled_fields ? `${summary.avg_filled_fields}` : "\u2014";
  el("stat-high").textContent = breakdown.high || 0;
  el("stat-issues").textContent = summary.rows_with_issues || 0;
}

// ---------- Presets ----------

function showDynamicFields(visible) {
  el("dynamicFields").hidden = !visible;
}

function clearFormFields() {
  ["sb_mpn", "sb_desc", "sb_dib", "sb_e1", "sb_unilog", "sb_manuf"].forEach((id) => {
    el(id).value = "";
  });
}

async function loadPresets() {
  try {
    const res = await fetch("/api/presets");
    presetsData = await res.json();
  } catch (err) {
    return;
  }
  const select = el("presetSelect");
  select.innerHTML = '<option value="">Select a sample…</option>';
  presetsData.forEach((p, idx) => {
    const opt = document.createElement("option");
    opt.value = String(idx);
    opt.textContent = p.name;
    select.appendChild(opt);
  });
  const custom = document.createElement("option");
  custom.value = "custom";
  custom.textContent = "Custom part";
  select.appendChild(custom);
}

function applyPreset(idx) {
  const p = presetsData[idx];
  if (!p) return;
  el("sb_mpn").value = p.Mfg_Part_Num || "";
  el("sb_desc").value = p.Part_Desc || "";
  el("sb_dib").value = p.DIB_Brand || "";
  el("sb_e1").value = p.E1_Brand || "";
  el("sb_unilog").value = p.Unilog_Brand || "";
  el("sb_manuf").value = p.Part_Manuf || "";
}

el("presetSelect").addEventListener("change", () => {
  const idx = el("presetSelect").value;
  if (idx === "") {
    clearFormFields();
    showDynamicFields(false);
    resetResultPanel();
    return;
  }
  if (idx === "custom") {
    clearFormFields();
    showDynamicFields(true);
    resetResultPanel();
    el("sb_mpn").focus();
    return;
  }
  applyPreset(Number(idx));
  showDynamicFields(true);
  resetResultPanel();
});

// ---------- Single enrichment ----------

function resetResultPanel() {
  el("wbOutput").hidden = true;
  el("sb-result-container").innerHTML = "";
  el("sbOpenDrawerBtn").hidden = true;
}

async function runSandboxEnrichment() {
  const btn = el("sbEnrichBtn");
  const container = el("sb-result-container");

  btn.disabled = true;
  btn.textContent = "Enriching\u2026";
  currentSandboxPreview = null;
  el("wbOutput").hidden = false;
  el("sbOpenDrawerBtn").hidden = true;

  container.innerHTML =
    '<div class="skeleton skeleton-line short" style="height:22px;margin-bottom:0.75rem"></div>' +
    '<div class="skeleton skeleton-line mid" style="height:14px"></div>' +
    '<div class="skeleton skeleton-line" style="height:55px;margin-top:0.75rem"></div>' +
    '<div class="skeleton skeleton-line" style="height:55px"></div>' +
    '<div class="skeleton skeleton-line" style="height:90px"></div>';

  const payload = {
    Mfg_Part_Num: el("sb_mpn").value.trim(),
    Part_Desc: el("sb_desc").value.trim(),
    DIB_Brand: el("sb_dib").value.trim(),
    E1_Brand: el("sb_e1").value.trim(),
    Unilog_Brand: el("sb_unilog").value.trim(),
    Part_Manuf: el("sb_manuf").value.trim(),
  };

  try {
    const res = await fetch("/api/enrich/single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || `HTTP ${res.status}`);
    const data = await res.json();
    currentSandboxPreview = data.preview;
    renderSandboxOutput(data.preview);
    el("sbOpenDrawerBtn").hidden = false;
  } catch (err) {
    resetResultPanel();
    showToast("Enrichment failed: " + err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Enrich";
  }
}

function renderSandboxOutput(p) {
  const container = el("sb-result-container");
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
        <span class="result-conf">${escapeHtml(p.confidence_band)}</span>
      </div>
    </div>

    ${
      descs.length
        ? `<table class="result-table">
      <caption>Descriptions</caption>
      <tbody>
        ${descs
          .slice(0, 5)
          .map(
            (d) => `
          <tr>
            <th>${escapeHtml(d.title)}</th>
            <td>${escapeHtml(d.value)}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`
        : ""
    }

    ${
      specs.length
        ? `<table class="result-table" style="margin-top:1.75rem">
      <caption>Attributes · ${specs.length} populated</caption>
      <tbody>
        ${specs
          .slice(0, 16)
          .map(
            (s) => `
          <tr>
            <th>${escapeHtml(s.label)}</th>
            <td>
              ${escapeHtml(s.display)}
              ${s.source ? `<span class="result-source">${escapeHtml(s.source)}</span>` : ""}
            </td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`
        : ""
    }
  `;
}

el("playgroundForm").addEventListener("submit", (e) => {
  e.preventDefault();
  runSandboxEnrichment();
});

el("playgroundResetBtn").addEventListener("click", () => {
  el("playgroundForm").reset();
  el("presetSelect").value = "";
  clearFormFields();
  showDynamicFields(false);
  resetResultPanel();
  currentSandboxPreview = null;
});

el("sbOpenDrawerBtn").addEventListener("click", () => {
  if (currentSandboxPreview) openDrawer(currentSandboxPreview);
});

// ---------- Catalog ----------

function rebuildCategoryOptions() {
  const sel = el("categoryFilter");
  const current = sel.value;
  const opts = new Map();
  taxonomyTemplates.forEach((t) => {
    if (t.category_id) opts.set(t.category_id, t.product_name || t.fine || t.category_id);
  });
  (lastData.previews || []).forEach((p) => {
    if (p.category_id && !opts.has(p.category_id)) {
      opts.set(p.category_id, p.taxonomy.Fine || p.taxonomy.Classpath || p.category_id);
    }
  });

  sel.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All categories";
  sel.appendChild(all);
  [...opts.entries()]
    .sort((a, b) => a[1].localeCompare(b[1]))
    .forEach(([id, label]) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = label;
      sel.appendChild(opt);
    });
  if ([...sel.options].some((o) => o.value === current)) sel.value = current;
}

async function loadTaxonomyOptions() {
  try {
    const res = await fetch("/api/taxonomy");
    const data = await res.json();
    taxonomyTemplates = data.templates || [];
  } catch (_) {
    taxonomyTemplates = [];
  }
  rebuildCategoryOptions();
}

function renderResults() {
  const body = el("results-body");
  const filterText = el("searchInput").value.toLowerCase();
  const catFilter = el("categoryFilter").value;
  const confFilter = el("confidenceFilter").value;

  const previews = (lastData.previews || []).filter((row) => {
    if (catFilter && row.category_id !== catFilter) return false;
    if (confFilter && row.confidence_band !== confFilter) return false;
    if (!filterText) return true;
    const hay =
      `${row.mpn} ${row.identity.BRAND_NAME || ""} ${row.identity.MANUFACTURER_NAME || ""} ` +
      `${row.taxonomy.Fine || ""} ${row.taxonomy.Classpath || ""} ${row.storefront_title || ""}`;
    return hay.toLowerCase().includes(filterText);
  });

  el("gridCountLabel").textContent = `Showing ${previews.length} of ${(lastData.previews || []).length} products`;

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

  body.innerHTML = previews
    .map((row) => {
      const cat = row.taxonomy.Fine || row.taxonomy.Classpath || "Generic Industrial";
      return `
      <tr data-mpn="${escapeHtml(row.mpn)}">
        <td>
          <div class="cell-mpn">${escapeHtml(row.mpn)}</div>
          <div class="cell-brand">${escapeHtml(row.identity.BRAND_NAME || row.identity.Part_Manuf || "\u2014")}</div>
        </td>
        <td>${escapeHtml(row.identity.MANUFACTURER_NAME || row.identity.Part_Manuf || "\u2014")}</td>
        <td class="cell-dim">${escapeHtml(cat)}</td>
        <td class="fields-cell">
          <div class="fields-line"><span>${row.filled_fields} / ${TOTAL_COLUMNS}</span><span class="pct">${row.completeness_pct}%</span></div>
          <div class="mini-bar"><span style="width:${row.completeness_pct}%"></span></div>
        </td>
        <td class="cell-dim">${row.evidence_count}</td>
        <td><span class="conf-text ${row.confidence_band}">${escapeHtml(row.confidence_band)}</span></td>
        <td style="text-align:right">
          <button class="btn btn-ghost btn-sm inspect-btn" type="button">Inspect</button>
        </td>
      </tr>`;
    })
    .join("");
}

el("results-body").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-mpn]");
  if (!tr) return;
  const row = (lastData.previews || []).find((p) => p.mpn === tr.dataset.mpn);
  if (row) openDrawer(row);
});

el("searchInput").addEventListener("input", renderResults);
el("categoryFilter").addEventListener("change", renderResults);
el("confidenceFilter").addEventListener("change", renderResults);

async function loadLastRun() {
  let data;
  try {
    const res = await fetch("/api/last-run");
    if (!res.ok) return;
    data = await res.json();
  } catch (_) {
    return;
  }
  if (data.summary && data.summary.rows) {
    lastData = data;
    renderDashboard();
    rebuildCategoryOptions();
    renderResults();
  }
}

el("refreshBtn").addEventListener("click", loadLastRun);

// ---------- Drawer ----------

const drawer = el("drawer");

function setDrawerTab(name) {
  document.querySelectorAll(".drawer-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.dtab === name);
  });
  document.querySelectorAll(".drawer-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `dtab-${name}`);
  });
}

document.querySelectorAll(".drawer-tab").forEach((btn) => {
  btn.addEventListener("click", () => setDrawerTab(btn.dataset.dtab));
});

function openDrawer(row, { silent = false } = {}) {
  if (!row) return;
  lastFocusedElement = silent ? lastFocusedElement : document.activeElement;

  const brand = row.identity.BRAND_NAME || row.identity.MANUFACTURER_NAME || "Manufacturer Direct";
  const cat = row.taxonomy.Fine || row.taxonomy.Classpath || "Industrial SKU";

  el("drawerMpn").textContent = row.mpn;
  el("drawerMeta").textContent = `${brand} \u2022 ${cat} \u2022 ${row.filled_fields} / ${TOTAL_COLUMNS} fields (${row.completeness_pct}%)`;

  const confBadge = el("drawerConfidenceBadge");
  confBadge.className = "drawer-conf";
  confBadge.textContent = row.confidence_band;

  renderRecordTab(row);
  renderEvidenceTab(row);
  renderAuditTab(row);

  setDrawerTab("record");
  drawer.classList.add("open");
  el("drawerBackdrop").classList.add("open");

  if (!silent) {
    drawerReturnHash = location.hash.startsWith("#/record/") ? "#/catalog" : location.hash || "#/catalog";
    if (drawerReturnHash === "#/enrich") drawerReturnHash = "#/enrich";
    setHash(`#/record/${encodeURIComponent(row.mpn)}`);
  }
  el("drawerClose").focus();
}

function hideDrawer() {
  drawer.classList.remove("open");
  el("drawerBackdrop").classList.remove("open");
}

function closeDrawer() {
  if (!drawer.classList.contains("open")) return;
  hideDrawer();
  go(drawerReturnHash);
  if (lastFocusedElement && document.contains(lastFocusedElement)) {
    lastFocusedElement.focus();
  }
}

el("drawerClose").addEventListener("click", closeDrawer);
el("drawerBackdrop").addEventListener("click", closeDrawer);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && drawer.classList.contains("open")) closeDrawer();
});

drawer.addEventListener("keydown", (e) => {
  if (e.key !== "Tab") return;
  const focusables = drawer.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
});

function kvTable(rows) {
  return `
    <table class="drawer-table">
      <tbody>
        ${rows
          .map(
            ([k, v]) => `
          <tr>
            <th>${escapeHtml(k)}</th>
            <td>${escapeHtml(v || "—")}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

function renderRecordTab(p) {
  const brand = p.identity.BRAND_NAME || p.identity.MANUFACTURER_NAME || "Manufacturer Direct";
  const descs = p.descriptions_list || [];
  const features = p.features || [];
  const specs = p.specs || [];

  const inputRows = Object.entries(p.input || {});
  const enrichedRows = [
    ["Brand / manufacturer", `${brand} / ${p.identity.MANUFACTURER_NAME || "—"}`],
    ["Category", p.taxonomy.Classpath || "—"],
    ["Fields filled", `${p.filled_fields} / ${TOTAL_COLUMNS}`],
    ["Sources", String(p.evidence_count)],
    ["Confidence", p.confidence_band],
  ];

  el("dtab-record").innerHTML = `
    <section class="drawer-section">
      <h3>Input</h3>
      ${kvTable(inputRows)}
    </section>
    <section class="drawer-section">
      <h3>Enriched</h3>
      ${kvTable(enrichedRows)}
    </section>
    <section class="drawer-section">
      <h3>Descriptions</h3>
      ${
        descs.length
          ? descs
              .map(
                (d) => `
        <div class="drawer-block">
          <div class="drawer-block-head">
            <span>${escapeHtml(d.title)}</span>
            <span class="drawer-block-meta">${d.length}${d.max_len ? " / " + d.max_len : ""}</span>
            <button class="copy-btn" type="button" data-copy-key="${regCopy(d.value)}">Copy</button>
          </div>
          <p>${escapeHtml(d.value)}</p>
        </div>`
              )
              .join("")
          : "<p>No descriptions generated.</p>"
      }
    </section>
    ${
      features.length
        ? `
    <section class="drawer-section">
      <h3>Item features</h3>
      <ul class="feature-list">${features.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>
    </section>`
        : ""
    }
    <section class="drawer-section">
      <h3>Attributes</h3>
      ${
        specs.length
          ? `
      <table class="drawer-table">
        <thead>
          <tr><th>Attribute</th><th>Value</th><th>Source</th></tr>
        </thead>
        <tbody>
          ${specs
            .map(
              (s) => `
            <tr>
              <th>${escapeHtml(s.label)}</th>
              <td>${escapeHtml(s.display)}</td>
              <td>${s.source ? escapeHtml(s.source) : "—"}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`
          : "<p>No attributes populated for this part.</p>"
      }
    </section>
  `;
}

function renderEvidenceTab(p) {
  const sources = Object.entries(p.sources || {});
  const blanks = TOTAL_COLUMNS - p.filled_fields;

  el("dtab-evidence").innerHTML = `
    <p class="drawer-note">${blanks} of ${TOTAL_COLUMNS} columns are blank because no manufacturer evidence was found.</p>
    ${
      sources.length
        ? `
    <table class="drawer-table">
      <thead>
        <tr><th>Source</th><th>URL</th></tr>
      </thead>
      <tbody>
        ${sources
          .map(
            ([k, v]) => `
          <tr>
            <th>${escapeHtml(k)}</th>
            <td><a href="${escapeHtml(v)}" target="_blank" rel="noopener noreferrer">${escapeHtml(v)}</a></td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`
        : "<p>No source URLs captured for this record.</p>"
    }
  `;
}

function renderAuditTab(p) {
  const issues = p.issues || [];
  const popFields = p.populated_fields || [];

  el("dtab-audit").innerHTML = `
    <p class="drawer-note">${
      issues.length
        ? `${issues.length} finding${issues.length > 1 ? "s" : ""} to review before publishing.`
        : "No validation issues. List-of-values, unit, and character-limit checks passed."
    }</p>
    ${issues.map((i) => `<p class="drawer-issue">${escapeHtml(i)}</p>`).join("")}

    <section class="drawer-section">
      <h3>Populated columns · ${popFields.length}</h3>
      <input type="search" class="raw-filter" placeholder="Filter columns…" aria-label="Filter columns" />
      <table class="drawer-table raw-table">
        <thead>
          <tr><th>Column</th><th>Value</th></tr>
        </thead>
        <tbody>
          ${popFields
            .map(
              (f) => `
            <tr>
              <th>${escapeHtml(f.field)}</th>
              <td>${escapeHtml(f.value)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </section>
  `;

  const filterInput = el("dtab-audit").querySelector(".raw-filter");
  filterInput.addEventListener("input", () => {
    const q = filterInput.value.toLowerCase();
    el("dtab-audit")
      .querySelectorAll(".raw-table tbody tr")
      .forEach((tr) => {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
  });
}

// ---------- Batch: sample stream ----------

function appendLog(tag, line) {
  const log = el("progress-log");
  const timestamp = new Date().toISOString().substring(11, 19);
  log.textContent += `[${timestamp}] [${tag}] ${line}\n`;
  log.scrollTop = log.scrollHeight;
}

function setProgressMessage(html) {
  el("progress-message").innerHTML = html;
}

async function runLiveEnrichment() {
  const limit = el("sampleLimit").value || "10";
  const filter = el("sampleFilter").value;
  const btn = el("liveBtn");
  const uploadBtn = el("uploadBtn");
  const progressWrap = el("batch-progress");

  btn.disabled = true;
  uploadBtn.disabled = true;
  progressWrap.hidden = false;
  el("progress-log").textContent = "";
  setProgressMessage(`Starting batch \u2014 ${limit} rows${filter ? `, segment: ${filter}` : ""}\u2026`);
  el("progress-fill").style.width = "0%";
  el("stat-rows").textContent = "0";

  try {
    const res = await fetch(`/api/enrich/stream?limit=${encodeURIComponent(limit)}&filter=${encodeURIComponent(filter)}`);
    if (!res.ok || !res.body) throw new Error(`Stream failed (HTTP ${res.status})`);
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
        }

        if (payload.type === "step") {
          setProgressMessage(`${escapeHtml(payload.mpn)} \u00b7 ${payload.current} / ${payload.total}`);
          el("progress-fill").style.width = `${Math.round(((payload.current - 0.5) / payload.total) * 100)}%`;
        }

        if (payload.type === "row") {
          appendLog("ENRICHED", `${payload.mpn} -> ${payload.brand || "MFR"} | ${payload.category || "classified"} (${payload.filled} fields, ${payload.confidence})`);
          el("stat-rows").textContent = payload.current;
          el("progress-fill").style.width = `${Math.round((payload.current / payload.total) * 100)}%`;
        }

        if (payload.type === "complete") {
          el("progress-fill").style.width = "100%";
          lastData = {
            filter: payload.filter,
            summary: payload.summary,
            previews: payload.previews,
            rows: payload.rows,
          };
          renderDashboard();
          rebuildCategoryOptions();
          renderResults();
          appendLog("SUCCESS", "Delivery written: upload_output.csv, enriched.xlsx, field_provenance.json");
          setProgressMessage(
            `Complete \u2014 ${payload.rows} SKUs enriched into the 252-column delivery format. <a href="#/catalog">View catalog</a>`
          );
        }
      }
    }
  } catch (err) {
    setProgressMessage(`Error: ${escapeHtml(err.message)}`);
    appendLog("ERROR", err.message);
    showToast("Batch interrupted", true);
  } finally {
    btn.disabled = false;
    uploadBtn.disabled = !el("file").files.length;
  }
}

el("liveBtn").addEventListener("click", runLiveEnrichment);

// ---------- Batch: CSV upload ----------

const fileInput = el("file");
const dropzone = el("dropzone");

function acceptFile(file) {
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  el("dropzone-label").textContent = file.name;
  dropzone.classList.add("has-file");
  el("uploadBtn").disabled = false;
}

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) acceptFile(fileInput.files[0]);
});

dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});

["dragenter", "dragover"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (file) acceptFile(file);
});

async function runUpload() {
  if (!fileInput.files.length) {
    showToast("Choose a CSV file first", true);
    return;
  }
  const uploadBtn = el("uploadBtn");
  const liveBtn = el("liveBtn");
  uploadBtn.disabled = true;
  liveBtn.disabled = true;
  el("batch-progress").hidden = false;
  el("progress-log").textContent = "";
  setProgressMessage("Uploading and processing batch\u2026");
  el("progress-fill").style.width = "35%";

  const form = new FormData();
  form.append("file", fileInput.files[0]);
  form.append("limit", "0");

  try {
    const res = await fetch("/enrich", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    lastData = data;
    renderDashboard();
    rebuildCategoryOptions();
    renderResults();
    el("progress-fill").style.width = "100%";
    setProgressMessage(
      `Complete \u2014 ${data.rows} SKUs enriched from your file. <a href="#/catalog">View catalog</a>`
    );
    appendLog("SUCCESS", `Uploaded file enriched (${data.rows} rows)`);
  } catch (err) {
    el("progress-fill").style.width = "0%";
    setProgressMessage(`Error: ${escapeHtml(err.message)}`);
    showToast("Upload failed: " + err.message, true);
  } finally {
    uploadBtn.disabled = false;
    liveBtn.disabled = false;
  }
}

el("uploadBtn").addEventListener("click", runUpload);

// ---------- Bootstrap ----------

route();
loadPresets();
loadTaxonomyOptions();
loadLastRun();
