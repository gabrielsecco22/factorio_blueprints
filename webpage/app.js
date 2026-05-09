/* Factorio Blueprint Tools Catalog - vanilla JS, no frameworks */

(function () {
  "use strict";

  // ---------- Seed dataset (fallback if data/*.json fetches fail) ----------

  const SEED_OSS = [
    {
      id: "factorio-blueprint-editor",
      name: "Factorio Blueprint Editor (FBE)",
      category: "visual-editor",
      description: "In-browser visual blueprint editor and viewer. Drag-and-drop entities, paste blueprint strings, preview belt/wire connections.",
      homepage: "https://fbe.teoxoy.com/",
      demo: "https://fbe.teoxoy.com/",
      source: "https://github.com/teoxoy/factorio-blueprint-editor",
      open_source: true,
      ready_2_0: false,
      space_age: false,
      maintained: "stale",
      last_commit: null,
      notes: "Last released for 1.x; 2.0 entities not supported."
    },
    {
      id: "factoriolab",
      name: "FactorioLab",
      category: "calculator",
      description: "Recipe and production-rate calculator covering Factorio plus several Satisfactory/Dyson Sphere flavors. Web-based, supports 2.0 + Space Age.",
      homepage: "https://factoriolab.github.io/",
      demo: "https://factoriolab.github.io/",
      source: "https://github.com/factoriolab/factoriolab",
      open_source: true,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null,
      notes: "Successor to factorio-lab; actively maintained."
    },
    {
      id: "kirkmcdonald",
      name: "Kirk McDonald Calculator",
      category: "calculator",
      description: "Long-running web calculator for Factorio production ratios, belts, beacons, and modules.",
      homepage: "https://kirkmcdonald.github.io/calc.html",
      demo: "https://kirkmcdonald.github.io/calc.html",
      source: "https://github.com/KirkMcDonald/kirkmcdonald.github.io",
      open_source: true,
      ready_2_0: false,
      space_age: false,
      maintained: "aging",
      last_commit: null,
      notes: "Classic 1.1 calculator; 2.0 data not yet ingested."
    },
    {
      id: "factorio-draftsman",
      name: "factorio-draftsman",
      category: "library",
      description: "Python library for programmatically building, validating, and serializing Factorio blueprint strings.",
      homepage: "https://github.com/redruin1/factorio-draftsman",
      demo: null,
      source: "https://github.com/redruin1/factorio-draftsman",
      open_source: true,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null,
      notes: "Active 2.0 support; the de-facto Python toolkit."
    },
    {
      id: "helmod",
      name: "Helmod",
      category: "in-game-mod",
      description: "In-game production planner: factory layouts, beacon coverage, recipe trees. Supports Space Age recipes.",
      homepage: "https://mods.factorio.com/mod/helmod",
      demo: null,
      source: "https://github.com/Helfima/helmod",
      open_source: true,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null
    },
    {
      id: "factoriobin",
      name: "FactorioBin",
      category: "string-paste",
      description: "Pastebin for blueprint strings with rendered previews and shareable URLs.",
      homepage: "https://factoriobin.com/",
      demo: "https://factoriobin.com/",
      source: null,
      open_source: false,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null
    }
  ];

  const SEED_COMMUNITY = [
    {
      id: "factorioprints",
      name: "Factorio Prints",
      category: "string-paste",
      description: "Community blueprint sharing site with screenshots, tags, and search.",
      homepage: "https://factorioprints.com/",
      demo: "https://factorioprints.com/",
      source: "https://github.com/oorzkws/FactorioBlueprintWebsite",
      open_source: true,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null
    },
    {
      id: "factorio-school",
      name: "Factorio School",
      category: "string-paste",
      description: "Curated blueprint library; mirrors Factorio Prints submissions and adds moderation.",
      homepage: "https://www.factorio.school/",
      demo: "https://www.factorio.school/",
      source: null,
      open_source: false,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null
    },
    {
      id: "recipe-book",
      name: "Recipe Book",
      category: "in-game-mod",
      description: "In-game recipe explorer: ingredients, products, machines, and unlocks. Lightweight reference companion to planners.",
      homepage: "https://mods.factorio.com/mod/RecipeBook",
      demo: null,
      source: "https://github.com/raiguard/RecipeBook",
      open_source: true,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null
    },
    {
      id: "factory-planner",
      name: "Factory Planner",
      category: "in-game-mod",
      description: "In-game production planner with machine/module configuration and Space Age support.",
      homepage: "https://mods.factorio.com/mod/factoryplanner",
      demo: null,
      source: "https://github.com/ClaudeMetz/FactoryPlanner",
      open_source: true,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null
    },
    {
      id: "rate-calculator",
      name: "Rate Calculator",
      category: "in-game-mod",
      description: "Selection-tool mod by raiguard: highlights an area in-game and reports throughput / ratios.",
      homepage: "https://mods.factorio.com/mod/RateCalculator",
      demo: null,
      source: "https://github.com/raiguard/RateCalculator",
      open_source: true,
      ready_2_0: true,
      space_age: true,
      maintained: "active",
      last_commit: null
    }
  ];

  // ---------- Constants & utilities ----------

  const CATEGORY_LABEL = {
    "visual-editor": "Visual editor",
    "calculator": "Calculator",
    "string-paste": "String paste",
    "renderer": "Renderer",
    "in-game-mod": "In-game mod",
    "library": "Library"
  };

  const STATUS_LABEL = {
    active: "Active (< 12 mo)",
    aging: "Aging (12-24 mo)",
    stale: "Stale (> 24 mo)",
    unknown: "Status unknown"
  };

  function classifyStatus(tool) {
    if (tool.maintained && STATUS_LABEL[tool.maintained]) return tool.maintained;
    if (!tool.last_commit) return "unknown";
    const then = Date.parse(tool.last_commit);
    if (Number.isNaN(then)) return "unknown";
    const months = (Date.now() - then) / (1000 * 60 * 60 * 24 * 30.44);
    if (months < 12) return "active";
    if (months < 24) return "aging";
    return "stale";
  }

  function sortTools(a, b) {
    const aReady = (a.ready_2_0 ? 1 : 0) + (a.space_age ? 1 : 0);
    const bReady = (b.ready_2_0 ? 1 : 0) + (b.space_age ? 1 : 0);
    if (aReady !== bReady) return bReady - aReady;
    const aActive = classifyStatus(a) === "active" ? 1 : 0;
    const bActive = classifyStatus(b) === "active" ? 1 : 0;
    if (aActive !== bActive) return bActive - aActive;
    return a.name.localeCompare(b.name);
  }

  function dedupe(oss, community) {
    const ossIds = new Set(oss.map((t) => t.id));
    return community.filter((t) => !ossIds.has(t.id));
  }

  async function fetchJson(path) {
    try {
      const r = await fetch(path, { cache: "no-cache" });
      if (!r.ok) return null;
      return await r.json();
    } catch (_e) {
      return null;
    }
  }

  // ---------- Filter state (persisted in URL hash) ----------

  const state = {
    category: "all",
    flags: new Set()
  };

  function readHash() {
    const h = window.location.hash.replace(/^#/, "");
    if (!h) return;
    const params = new URLSearchParams(h);
    if (params.has("category")) state.category = params.get("category");
    if (params.has("flags")) {
      const flags = params.get("flags").split(",").filter(Boolean);
      state.flags = new Set(flags);
    }
  }

  function writeHash() {
    const params = new URLSearchParams();
    if (state.category && state.category !== "all") params.set("category", state.category);
    if (state.flags.size) params.set("flags", Array.from(state.flags).join(","));
    const next = params.toString();
    const target = next ? "#" + next : "";
    if (window.location.hash !== target) {
      history.replaceState(null, "", window.location.pathname + window.location.search + target);
    }
  }

  function passesFilters(tool) {
    if (state.category !== "all" && tool.category !== state.category) return false;
    for (const flag of state.flags) {
      if (!tool[flag]) return false;
    }
    return true;
  }

  // ---------- Rendering ----------

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") node.className = v;
        else if (k === "text") node.textContent = v;
        else if (k.startsWith("data-")) node.setAttribute(k, v);
        else if (k === "html") node.innerHTML = v;
        else if (k === "hidden" && v) node.hidden = true;
        else node.setAttribute(k, v);
      }
    }
    if (children) {
      for (const c of children) {
        if (c == null) continue;
        node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
      }
    }
    return node;
  }

  function renderCard(tool) {
    const status = classifyStatus(tool);
    const categoryLabel = CATEGORY_LABEL[tool.category] || tool.category;

    const badges = el("div", { class: "badges" }, [
      el("span", { class: "badge category", text: categoryLabel }),
      tool.ready_2_0 ? el("span", { class: "badge compat", text: "2.0" }) : null,
      tool.space_age ? el("span", { class: "badge compat", text: "Space Age" }) : null,
      tool.open_source
        ? el("span", { class: "badge oss", text: "Open source" })
        : el("span", { class: "badge closed", text: "Closed source" })
    ]);

    const head = el("div", { class: "card-head" }, [
      el("h3", { class: "card-name" }, [
        el("a", { href: tool.homepage, target: "_blank", rel: "noopener", text: tool.name })
      ]),
      el("span", {
        class: "status",
        "data-status": status,
        title: STATUS_LABEL[status] || status,
        text: STATUS_LABEL[status] || status
      })
    ]);

    const desc = el("p", { class: "card-desc", text: tool.description || "" });

    const linkRow = el("div", { class: "card-links" }, [
      tool.homepage
        ? el("a", { href: tool.homepage, target: "_blank", rel: "noopener" }, [
            el("span", { class: "label", text: "Home" }),
            "Open"
          ])
        : null,
      tool.demo && tool.demo !== tool.homepage
        ? el("a", { href: tool.demo, target: "_blank", rel: "noopener" }, [
            el("span", { class: "label", text: "Demo" }),
            "Try"
          ])
        : null,
      tool.source
        ? el("a", { href: tool.source, target: "_blank", rel: "noopener" }, [
            el("span", { class: "label", text: "Source" }),
            "Code"
          ])
        : null
    ]);

    return el("article", { class: "card", "data-id": tool.id }, [head, badges, desc, linkRow]);
  }

  function renderGrid(gridEl, emptyEl, tools) {
    gridEl.innerHTML = "";
    const visible = tools.filter(passesFilters).sort(sortTools);
    for (const t of visible) gridEl.appendChild(renderCard(t));
    if (visible.length === 0) {
      emptyEl.hidden = false;
    } else {
      emptyEl.hidden = true;
    }
    return visible.length;
  }

  // ---------- Wire up ----------

  function syncChips() {
    document.querySelectorAll('[data-filter="category"] .chip').forEach((btn) => {
      btn.setAttribute("aria-pressed", btn.dataset.value === state.category ? "true" : "false");
    });
    document.querySelectorAll('[data-filter="flags"] .chip').forEach((btn) => {
      btn.setAttribute("aria-pressed", state.flags.has(btn.dataset.value) ? "true" : "false");
    });
  }

  function bindChips(rerender) {
    document.querySelectorAll('[data-filter="category"] .chip').forEach((btn) => {
      btn.addEventListener("click", () => {
        state.category = btn.dataset.value;
        syncChips();
        writeHash();
        rerender();
      });
    });
    document.querySelectorAll('[data-filter="flags"] .chip').forEach((btn) => {
      btn.addEventListener("click", () => {
        const v = btn.dataset.value;
        if (state.flags.has(v)) state.flags.delete(v);
        else state.flags.add(v);
        syncChips();
        writeHash();
        rerender();
      });
    });
    document.getElementById("reset-filters").addEventListener("click", () => {
      state.category = "all";
      state.flags = new Set();
      syncChips();
      writeHash();
      rerender();
    });
  }

  function setBanner(message) {
    const b = document.getElementById("banner");
    if (!message) {
      b.hidden = true;
      b.textContent = "";
      return;
    }
    b.hidden = false;
    b.textContent = message;
  }

  function setLastRefreshed(meta) {
    const node = document.getElementById("last-refreshed");
    if (meta && meta.last_built) {
      try {
        const d = new Date(meta.last_built);
        node.textContent = d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
        return;
      } catch (_e) {}
    }
    node.textContent = "unknown (run webpage/build.py)";
  }

  async function init() {
    readHash();
    syncChips();

    const [ossData, communityData, meta] = await Promise.all([
      fetchJson("data/oss_tools.json"),
      fetchJson("data/community_tools.json"),
      fetchJson("data/last_built.json")
    ]);

    let oss = Array.isArray(ossData) ? ossData : (ossData && Array.isArray(ossData.tools) ? ossData.tools : null);
    let community = Array.isArray(communityData) ? communityData : (communityData && Array.isArray(communityData.tools) ? communityData.tools : null);

    const messages = [];
    if (!oss) {
      oss = SEED_OSS.slice();
      messages.push("OSS data file not found");
    }
    if (!community) {
      community = SEED_COMMUNITY.slice();
      messages.push("community data file not found");
    }
    if (messages.length) {
      setBanner("Using fallback seed data (" + messages.join(", ") + "). Run webpage/build.py after sibling agents finish.");
    }

    community = dedupe(oss, community);
    setLastRefreshed(meta);

    const ossGrid = document.getElementById("oss-grid");
    const ossEmpty = document.getElementById("oss-empty");
    const commGrid = document.getElementById("community-grid");
    const commEmpty = document.getElementById("community-empty");
    const countNode = document.getElementById("result-count");

    function rerender() {
      const a = renderGrid(ossGrid, ossEmpty, oss);
      const b = renderGrid(commGrid, commEmpty, community);
      countNode.textContent = String(a + b);
    }

    bindChips(rerender);
    rerender();

    window.addEventListener("hashchange", () => {
      readHash();
      syncChips();
      rerender();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
