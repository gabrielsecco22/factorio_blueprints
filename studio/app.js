/* Factudio frontend.
 * Vanilla JS, no frameworks. Talks to /api/* on the same origin.
 *
 * FBE integration: see INTEGRATION.md. The live demo at fbe.teoxoy.com
 * sets `frame-ancestors 'none'`, so we cannot iframe it. Instead we
 * open the editor in a new tab via the documented `?source=<bp>` URL
 * parameter (FBE accepts a raw blueprint string when it starts with `0`,
 * which all 2.0 strings do). The studio shows an ASCII grid preview +
 * the blueprint string + a markdown report in-page, and clicking
 * "Open in FBE editor" launches a real visual edit session.
 */

(function () {
  "use strict";

  const API = {
    health:     () => fetch("/api/health").then(j),
    recipes:    () => fetch("/api/recipes").then(j),
    machines:   () => fetch("/api/machines").then(j),
    belts:      () => fetch("/api/belts").then(j),
    items:      () => fetch("/api/items").then(j),
    quality:    () => fetch("/api/quality").then(j),
    research:   () => fetch("/api/research").then(j),
    library:    () => fetch("/api/library").then(j),
    synthesize: (body) => post("/api/synthesize", body),
    validate:   (body) => post("/api/validate", body),
    save:       (body) => post("/api/save", body),
  };

  function j(r) { return r.json(); }
  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then(j);
  }

  // ----------------------------------------------------------------- DOM
  const $ = (id) => document.getElementById(id);

  const els = {
    form: $("spec-form"),
    kind: $("kind"),
    target: $("target"),
    targetHint: $("target-hint"),
    rate: $("rate"),
    machineCount: $("machine_count"),
    machine: $("machine"),
    fuel: $("fuel"),
    fuelRow: $("fuel-row"),
    beltTier: $("belt_tier"),
    inserterTier: $("inserter_tier"),
    quality: $("quality"),
    research: $("research-grid"),
    mods: $("mods"),
    label: $("label"),
    itemsList: $("items-list"),
    btnGenerate: $("btn-generate"),
    btnSendFbe: $("btn-send-fbe"),
    btnImport: $("btn-import"),
    btnSave: $("btn-save"),
    btnCopy: $("btn-copy"),
    btnValidate: $("btn-validate"),
    btnRefreshLibrary: $("btn-refresh-library"),

    bpString: $("bp-string"),
    asciiPreview: $("ascii-preview"),
    previewSummary: $("preview-summary"),
    openFbe: $("open-fbe"),
    reportMd: $("report-md"),
    libraryList: $("library-list"),
    libraryCount: $("library-count"),
    stringWarn: $("string-warn"),

    statusHarness: $("status-harness"),
    statusLibrary: $("status-library"),
    statusFbe: $("status-fbe"),

    ratesTable: $("rates-table"),
    warningsList: $("warnings-list"),
  };

  // ----------------------------------------------------------------- state
  const state = {
    catalogs: {
      recipes: [],
      machines: [],
      belts: [],
      items: [],
      quality: [],
      research: [],
    },
    bpString: "",
    enabledMods: new Set(), // populated from health + items
    recipesByResultItem: new Map(), // item_name -> list[recipe]
    recipeCategoryToMachines: new Map(),
  };

  const FBE_BASE = "https://fbe.teoxoy.com";

  // ----------------------------------------------------------------- init
  init().catch((err) => {
    console.error(err);
    setStatus(els.statusHarness, "bad", `Harness: ${err.message || "error"}`);
  });

  async function init() {
    setStatus(els.statusHarness, "unknown", "Harness: checking...");
    setStatus(els.statusLibrary, "unknown", "Library: checking...");
    pingFbe();

    const [health, items, recipes, machines, belts, quality, research, library] =
      await Promise.all([
        API.health(),
        API.items(),
        API.recipes(),
        API.machines(),
        API.belts(),
        API.quality(),
        API.research(),
        API.library(),
      ]);

    state.catalogs.items = items;
    state.catalogs.recipes = recipes;
    state.catalogs.machines = machines;
    state.catalogs.belts = belts;
    state.catalogs.quality = quality;
    state.catalogs.research = research;

    // Build lookups.
    for (const r of recipes) {
      for (const res of (r.results || [])) {
        const arr = state.recipesByResultItem.get(res.name) || [];
        arr.push(r);
        state.recipesByResultItem.set(res.name, arr);
      }
    }

    setStatus(els.statusHarness, health.harness ? "ok" : "bad",
      `Harness: ${health.harness ? "ready" : (health.harness_error || "unavailable")}`);
    setStatus(els.statusLibrary, "ok",
      `Library: ${health.library_root} (${library.length} entries)`);

    populateItemsAutocomplete(items);
    populateBelts(belts);
    populateQuality(quality);
    populateResearch(research);
    populateMods(items, health.mods_enabled_count);
    refreshMachineDropdown();
    refreshTargetHint();
    renderLibrary(library);
    setupTabs();
    wireForm();
  }

  // ------------------------------------------------------------ FBE ping
  function pingFbe() {
    // We can't iframe fbe.teoxoy.com (CSP frame-ancestors none). We probe
    // reachability via a no-cors fetch -- this won't tell us *what* it
    // returned, but a network failure will reject. That's enough to surface
    // an "FBE unreachable" state to the user.
    fetch(FBE_BASE + "/", { mode: "no-cors", cache: "no-store" })
      .then(() => setStatus(els.statusFbe, "ok", "FBE editor: reachable"))
      .catch(() => setStatus(els.statusFbe, "bad", "FBE editor: unreachable"));
  }

  // ------------------------------------------------------------ Status bar
  function setStatus(el, status, label) {
    if (!el) return;
    el.dataset.status = status;
    el.textContent = label;
  }

  // -------------------------------------------------------- Populate UI
  function populateItemsAutocomplete(items) {
    const seen = new Set();
    for (const it of items) {
      if (seen.has(it.name)) continue;
      seen.add(it.name);
      const opt = document.createElement("option");
      opt.value = it.name;
      els.itemsList.appendChild(opt);
    }
  }

  function populateBelts(belts) {
    els.beltTier.innerHTML = "";
    for (const b of belts) {
      const opt = document.createElement("option");
      opt.value = b.name;
      const rate = (b.items_per_second_total || 0).toFixed(1);
      opt.textContent = `${b.name}  (${rate}/s)`;
      els.beltTier.appendChild(opt);
    }
    els.beltTier.value = "transport-belt";
  }

  function populateQuality(quality) {
    els.quality.innerHTML = "";
    for (const q of quality) {
      const opt = document.createElement("option");
      opt.value = q.name;
      opt.textContent = `${q.name} (level ${q.level || 0})`;
      els.quality.appendChild(opt);
    }
    els.quality.value = "normal";
  }

  function populateResearch(research) {
    els.research.innerHTML = "";
    // Show only the most "build-spec relevant" sliders.
    const interesting = [
      "mining-drill-productivity-bonus",
      "worker-robot-speed",
      "change-recipe-productivity",
    ];
    const list = research.filter((r) => interesting.includes(r));
    for (const r of list) {
      const row = document.createElement("div");
      row.className = "research-row";
      const lab = document.createElement("label");
      lab.textContent = r;
      lab.htmlFor = `r_${r}`;
      const inp = document.createElement("input");
      inp.type = "number";
      inp.min = "0";
      inp.step = "1";
      inp.value = "0";
      inp.id = `r_${r}`;
      inp.dataset.research = r;
      row.appendChild(lab);
      row.appendChild(inp);
      els.research.appendChild(row);
    }
    if (list.length === 0) {
      els.research.innerHTML = '<p class="hint">No research effects loaded.</p>';
    }
  }

  function populateMods(items, enabledCount) {
    const mods = new Set();
    for (const it of items) {
      if (it.from_mod) mods.add(it.from_mod);
    }
    state.enabledMods = mods;
    els.mods.innerHTML = "";
    const sorted = [...mods].sort();
    for (const m of sorted) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      opt.selected = true;
      els.mods.appendChild(opt);
    }
    if (sorted.length === 0) {
      els.mods.innerHTML = '<option disabled>(no mod attribution found)</option>';
    }
  }

  function refreshMachineDropdown() {
    const targetName = els.target.value.trim();
    const recipes = state.recipesByResultItem.get(targetName) || [];
    // Find a recipe that's not a recycling variant.
    const recipe = recipes.find((r) => !(r.category || "").endsWith("recycling"));
    let machines = [];
    if (recipe) {
      machines = state.catalogs.machines.filter((m) =>
        (m.crafting_categories || []).includes(recipe.category)
      );
    }
    if (machines.length === 0) {
      // Fallback: show all crafting machines so the user is not stuck.
      machines = state.catalogs.machines.filter((m) => (m.crafting_categories || []).length > 0);
    }
    const previous = els.machine.value;
    els.machine.innerHTML = "";
    for (const m of machines) {
      const opt = document.createElement("option");
      opt.value = m.name;
      opt.textContent = `${m.name}  (speed ${m.crafting_speed || "?"}, ${m.energy_source_type || "?"})`;
      els.machine.appendChild(opt);
    }
    if (previous && [...els.machine.options].some((o) => o.value === previous)) {
      els.machine.value = previous;
    }
    toggleFuelRow();
  }

  function toggleFuelRow() {
    const m = state.catalogs.machines.find((mm) => mm.name === els.machine.value);
    const burner = m && m.energy_source_type === "burner";
    els.fuelRow.style.display = burner ? "" : "none";
  }

  function refreshTargetHint() {
    const name = els.target.value.trim();
    const recipes = state.recipesByResultItem.get(name) || [];
    if (recipes.length === 0) {
      els.targetHint.textContent = "no recipe found for this item";
      return;
    }
    const r = recipes.find((x) => !(x.category || "").endsWith("recycling")) || recipes[0];
    els.targetHint.textContent = `recipe: ${r.name} (category=${r.category}, from_mod=${r.from_mod || "base"})`;
  }

  // ---------------------------------------------------------- Tabs
  function setupTabs() {
    const tabs = document.querySelectorAll(".tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const name = tab.dataset.tab;
        document.querySelectorAll(".tab").forEach((t) => {
          t.classList.toggle("active", t === tab);
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });
        document.querySelectorAll(".tab-pane").forEach((p) => {
          p.classList.toggle("active", p.id === "pane-" + name);
        });
      });
    });
  }

  // ---------------------------------------------------------- Form wiring
  function wireForm() {
    els.target.addEventListener("input", () => {
      refreshMachineDropdown();
      refreshTargetHint();
    });
    els.machine.addEventListener("change", toggleFuelRow);
    els.kind.addEventListener("change", onKindChange);

    els.form.addEventListener("submit", onGenerate);
    els.btnSendFbe.addEventListener("click", onSendToFbe);
    els.btnImport.addEventListener("click", onImportFromEditor);
    els.btnSave.addEventListener("click", onSaveToLibrary);
    els.btnCopy.addEventListener("click", onCopy);
    els.btnValidate.addEventListener("click", onValidate);
    els.btnRefreshLibrary.addEventListener("click", () => API.library().then(renderLibrary));
  }

  function onKindChange() {
    // Greying out target/rate doesn't make sense for solar -- the harness
    // ignores those fields. We just leave them; the harness treats them as
    // optional.
    const kind = els.kind.value;
    if (kind === "solar_field" || kind === "green_circuit_block") {
      els.targetHint.textContent = `kind=${kind} ignores 'target'`;
    } else {
      refreshTargetHint();
    }
  }

  function readSpec() {
    const research = {};
    document.querySelectorAll("[data-research]").forEach((inp) => {
      const v = parseInt(inp.value, 10);
      if (v > 0) research[inp.dataset.research] = v;
    });

    const spec = {
      kind: els.kind.value,
      target: els.target.value.trim() || null,
      machine_choice: els.machine.value || null,
      fuel: els.fuel.value,
      belt_tier: els.beltTier.value,
      inserter_tier: els.inserterTier.value,
      quality: els.quality.value,
      research_levels: research,
      label: els.label.value.trim() || null,
    };

    const rate = parseFloat(els.rate.value);
    const count = parseInt(els.machineCount.value, 10);
    if (!Number.isNaN(rate) && rate > 0) spec.output_rate_per_sec = rate;
    if (!Number.isNaN(count) && count > 0) spec.machine_count = count;

    return spec;
  }

  // ---------------------------------------------------------- Actions
  async function onGenerate(ev) {
    ev.preventDefault();
    const spec = readSpec();
    setBusy(true, "Synthesising...");
    try {
      const resp = await API.synthesize(spec);
      handleSynthesisResponse(resp);
    } catch (e) {
      addWarning("error", `network: ${e.message || e}`);
    } finally {
      setBusy(false);
    }
  }

  function handleSynthesisResponse(resp) {
    clearWarnings();
    renderModCompat(resp.mod_compat);
    (resp.warnings || []).forEach((w) => {
      const sub = w.suggested_substitute ? `  (try: ${w.suggested_substitute})` : "";
      addWarning(w.level || "info", (w.message || "") + sub);
    });

    if (!resp.blueprint_string) {
      els.previewSummary.textContent = "Synthesis failed -- see warnings.";
      els.openFbe.hidden = true;
      els.btnSendFbe.disabled = true;
      els.btnSave.disabled = true;
      els.asciiPreview.textContent = "";
      els.bpString.value = "";
      els.reportMd.textContent = resp.report_md || "";
      renderRates(resp.rates);
      return;
    }

    state.bpString = resp.blueprint_string;
    els.bpString.value = resp.blueprint_string;
    els.previewSummary.textContent =
      `${resp.entity_count || "?"} entities  -  ${resp.blueprint_string.length} chars`;
    els.openFbe.hidden = false;
    els.openFbe.href = fbeUrl(resp.blueprint_string);
    els.btnSendFbe.disabled = false;
    els.btnSave.disabled = false;
    els.reportMd.textContent = resp.report_md || "(no report)";
    renderAsciiPreview(resp);
    renderRates(resp.rates);
  }

  function fbeUrl(bp) {
    return `${FBE_BASE}/?source=${encodeURIComponent(bp)}`;
  }

  function onSendToFbe() {
    if (!state.bpString) return;
    window.open(fbeUrl(state.bpString), "_blank", "noopener");
  }

  async function onImportFromEditor() {
    // FBE doesn't postMessage anything to its parent, so the only reliable
    // import flow is: user copies the string out of FBE and pastes it here.
    // We surface that flow by jumping to the string tab and focusing the
    // textarea. If the textarea already has a string we validate it.
    document.querySelector('.tab[data-tab="string"]').click();
    els.bpString.focus();
    els.bpString.select();
    if ((els.bpString.value || "").trim().startsWith("0")) {
      onValidate();
    } else {
      els.stringWarn.textContent = "Paste a blueprint string here, then click Validate.";
    }
  }

  async function onValidate() {
    const s = (els.bpString.value || "").trim();
    if (!s) { els.stringWarn.textContent = "(empty)"; return; }
    setBusy(true, "Validating...");
    try {
      const resp = await API.validate({ string: s });
      if (!resp.ok) {
        els.stringWarn.textContent = `error: ${resp.error}`;
        addWarning("error", resp.error);
        return;
      }
      state.bpString = s;
      els.stringWarn.textContent =
        `${resp.entity_count} entities  -  label="${resp.label || ""}"  -  roundtrip=${resp.roundtrip_ok}`;
      els.previewSummary.textContent = els.stringWarn.textContent;
      els.openFbe.hidden = false;
      els.openFbe.href = fbeUrl(s);
      els.btnSendFbe.disabled = false;
      els.btnSave.disabled = false;

      clearWarnings();
      renderModCompat(resp.mod_compat);
      (resp.warnings || []).forEach((w) => addWarning(w.level || "info", w.message));

      // Render an ascii preview from the decoded entity positions.
      renderAsciiPreviewFromDecoded(resp.decoded);
    } catch (e) {
      els.stringWarn.textContent = `error: ${e.message || e}`;
    } finally {
      setBusy(false);
    }
  }

  function onCopy() {
    const s = els.bpString.value || "";
    if (!s) return;
    navigator.clipboard.writeText(s).then(() => {
      els.stringWarn.textContent = "copied to clipboard";
    }).catch((e) => {
      els.stringWarn.textContent = "copy failed: " + e;
    });
  }

  async function onSaveToLibrary() {
    if (!state.bpString) return;
    const name = prompt("Save as (optional):", els.label.value || "");
    setBusy(true, "Saving...");
    try {
      const resp = await API.save({ string: state.bpString, name: name || null });
      if (resp.ok) {
        addWarning("info", `saved to ${resp.path}`);
        const lib = await API.library();
        renderLibrary(lib);
      } else {
        addWarning("error", `save failed: ${resp.error}`);
      }
    } finally {
      setBusy(false);
    }
  }

  function setBusy(busy, label) {
    els.btnGenerate.disabled = busy;
    els.btnGenerate.textContent = busy ? (label || "Working...") : "Generate";
  }

  // ---------------------------------------------------------- Renderers
  function renderRates(rates) {
    const tbody = els.ratesTable.querySelector("tbody");
    tbody.innerHTML = "";
    if (!rates) {
      tbody.innerHTML = '<tr><td colspan="2" class="muted">no rate calc available</td></tr>';
      return;
    }
    if (rates.error) {
      tbody.innerHTML = `<tr><td colspan="2" class="muted">rate calc error: ${rates.error}</td></tr>`;
      return;
    }
    const rows = [
      ["recipe", rates.recipe],
      ["machine", `${rates.machine} x ${rates.machine_count}`],
      ["crafts/s/machine", fmt(rates.crafts_per_second_per_machine)],
      ["crafts/s total", fmt(rates.crafts_per_second_total)],
    ];
    for (const [name, v] of Object.entries(rates.outputs_per_second || {})) {
      rows.push([`out: ${name}`, fmt(v) + " /s"]);
    }
    for (const [name, v] of Object.entries(rates.inputs_per_second || {})) {
      rows.push([`in: ${name}`, fmt(v) + " /s"]);
    }
    rows.push(["power", fmt(rates.power_kw_total) + " kW"]);
    rows.push(["pollution", fmt(rates.pollution_per_minute_total) + " /min"]);
    for (const r of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="key">${esc(r[0])}</td><td class="num">${esc(r[1])}</td>`;
      tbody.appendChild(tr);
    }
    if ((rates.diagnostics || []).length) {
      for (const d of rates.diagnostics) addWarning("info", "rate-calc: " + d);
    }
  }

  function fmt(n) {
    if (n === null || n === undefined) return "-";
    if (typeof n !== "number") return String(n);
    if (Math.abs(n) >= 100) return n.toFixed(1);
    if (Math.abs(n) >= 1) return n.toFixed(2);
    return n.toFixed(4);
  }
  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function clearWarnings() { els.warningsList.innerHTML = ""; }

  function addWarning(level, message) {
    const li = document.createElement("li");
    li.className = level;
    li.textContent = message;
    els.warningsList.appendChild(li);
  }

  function renderModCompat(mc) {
    if (!mc) return;
    if ((mc.required || []).length) {
      const tag = (mc.missing || []).length ? "error" : "info";
      const msg = `mods required: ${(mc.required || []).join(", ")}` +
        (mc.missing && mc.missing.length ? `  -  MISSING: ${mc.missing.join(", ")}` : "");
      addWarning(tag, msg);
    }
  }

  function renderAsciiPreview(resp) {
    // We don't have entities directly, but we have entity_count and the report
    // includes a breakdown. Trigger a /api/validate to pull positions out.
    if (!resp.blueprint_string) { els.asciiPreview.textContent = ""; return; }
    API.validate({ string: resp.blueprint_string }).then((v) => {
      if (v.ok) renderAsciiPreviewFromDecoded(v.decoded);
    });
  }

  function renderAsciiPreviewFromDecoded(decoded) {
    if (!decoded) { els.asciiPreview.textContent = ""; return; }
    const body = decoded.blueprint || {};
    const ents = body.entities || [];
    if (ents.length === 0) { els.asciiPreview.textContent = "(no entities)"; return; }
    // Bounding box.
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const e of ents) {
      const x = (e.position && e.position.x) || 0;
      const y = (e.position && e.position.y) || 0;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
    minX = Math.floor(minX) - 1;
    minY = Math.floor(minY) - 1;
    maxX = Math.ceil(maxX) + 1;
    maxY = Math.ceil(maxY) + 1;
    const w = Math.min(maxX - minX + 1, 160);
    const h = Math.min(maxY - minY + 1, 60);
    if (w <= 0 || h <= 0) { els.asciiPreview.textContent = "(empty bbox)"; return; }
    const grid = Array.from({ length: h }, () => Array(w).fill(" "));
    for (const e of ents) {
      const x = Math.round((e.position && e.position.x) || 0) - minX;
      const y = Math.round((e.position && e.position.y) || 0) - minY;
      if (x < 0 || y < 0 || x >= w || y >= h) continue;
      grid[y][x] = symbolFor(e.name);
    }
    els.asciiPreview.textContent = grid.map((r) => r.join("")).join("\n");
  }

  function symbolFor(name) {
    if (!name) return "?";
    if (name.includes("furnace")) return "F";
    if (name.includes("assembling")) return "A";
    if (name.includes("transport-belt")) return "=";
    if (name.includes("inserter")) return "i";
    if (name.includes("solar-panel")) return "S";
    if (name.includes("accumulator")) return "B";
    if (name.includes("substation")) return "X";
    if (name.includes("electric-pole")) return "+";
    if (name.includes("pole")) return "+";
    if (name.includes("chest")) return "C";
    return name[0].toUpperCase();
  }

  function renderLibrary(library) {
    els.libraryList.innerHTML = "";
    els.libraryCount.textContent = `${library.length} entries`;
    if (library.length === 0) {
      els.libraryList.innerHTML = '<li class="muted">(empty)</li>';
      return;
    }
    for (const e of library) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "lib-name";
      name.textContent = e.name;
      const lab = document.createElement("span");
      lab.className = "lib-label";
      lab.textContent = e.label ? `"${e.label}"` : `(${e.kind})`;
      const btn = document.createElement("a");
      btn.className = "lib-action";
      btn.href = "#";
      btn.textContent = "load";
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        // We don't have a /api/library/<name> endpoint -- the path is the
        // server-rooted relative path; we surface it for the user.
        addWarning("info", `library entry path: ${e.path}`);
      });
      li.appendChild(name);
      li.appendChild(lab);
      li.appendChild(btn);
      els.libraryList.appendChild(li);
    }
  }
})();
