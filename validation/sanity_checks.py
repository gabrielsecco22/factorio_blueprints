#!/usr/bin/env python3
"""Cross-spec invariants for `specs/*.json`.

Stdlib only. Loads every spec, checks that names cross-reference cleanly,
and that derived numbers (belt throughput, inserter rotation time) match
what the docs claim. Prints PASS/FAIL counts and exits non-zero on
failure.

Run from repo root:
    python3 validation/sanity_checks.py
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SPECS = REPO / "specs"


def load(name: str):
    return json.loads((SPECS / name).read_text())


# -----------------------------------------------------------------------------
# tiny test harness
# -----------------------------------------------------------------------------
PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"FAIL  {label}" + (f"  ({detail})" if detail else ""))


def section(title: str) -> None:
    print(f"\n== {title} ==")


# -----------------------------------------------------------------------------
# load specs
# -----------------------------------------------------------------------------
items = load("items.json")
fluids = load("fluids.json")
recipes = load("recipes.json")
machines = load("machines.json")
beacons = load("beacons.json")
belts = load("belts.json")
inserters = load("inserters.json")
modules = load("modules.json")
robots = load("robots.json")
quality = load("quality.json")
planets = load("planets.json")
recipe_categories = load("recipe_categories.json")
research_effects = load("research_effects.json")
electric_network = load("electric_network.json")
entity_planet_restrictions = load("entity_planet_restrictions.json")
recipe_planet_restrictions = load("recipe_planet_restrictions.json")

# Indexed name sets
item_names = {it["name"] for it in items}
fluid_names = {fl["name"] for fl in fluids}
recipe_names = {r["name"] for r in recipes}
machine_names = {m["name"] for m in machines}
beacon_names = {b["name"] for b in beacons}
module_names = {m["name"] for m in modules}
belt_names = {b["name"] for b in belts}
inserter_names = {i["name"] for i in inserters}
quality_names = {q["name"] for q in quality}
planet_names = {p["name"] for p in planets}

# Names from electric_network and robots
electric_names: set[str] = set()
for cat in electric_network.values():
    for e in cat:
        electric_names.add(e["name"])
robot_names = {r["name"] for r in robots["robots"]} | {r["name"] for r in robots["roboports"]}

# All entity-like names (anything that could legitimately appear in
# entity_planet_restrictions). For things like rails / locomotives /
# special platform entities that aren't in any topic-specific spec,
# fall back to the raw prototype dump.
all_entity_like = (
    machine_names | beacon_names | belt_names | inserter_names
    | electric_names | robot_names | item_names
)

# Optionally consult the prototype dump for entity types that don't have
# a dedicated spec (rails, rolling stock, asteroid-collector, thruster,
# space-platform-hub, plant, fluid-turret, reactor, spider-vehicle, ...).
DUMP = SPECS / "data-raw-dump.json"
dump_entity_names: set[str] = set()
if DUMP.is_file():
    _dump = json.loads(DUMP.read_text())
    # Treat any prototype category whose name isn't obviously cosmetic as
    # a source of valid entity names. The check just needs membership.
    skip_categories = {
        "icon", "tile-effect", "noise-expression", "noise-function",
        "ambient-sound", "music-track", "sound", "shortcut", "tip-and-tricks-item",
        "achievement", "tutorial",
    }
    for cat, by_name in _dump.items():
        if cat in skip_categories:
            continue
        if isinstance(by_name, dict):
            dump_entity_names.update(by_name.keys())
all_entity_like |= dump_entity_names

# -----------------------------------------------------------------------------
# 1. Recipe ingredients/results resolve to items or fluids
# -----------------------------------------------------------------------------
section("recipe ingredient/result resolution")
all_ing_res_names: set[str] = set()
for r in recipes:
    for slot in r.get("ingredients", []) + r.get("results", []):
        n = slot["name"]
        all_ing_res_names.add(n)

unresolved = [n for n in sorted(all_ing_res_names) if n not in item_names and n not in fluid_names]
check(
    "every recipe ingredient/result is an item or fluid",
    not unresolved,
    f"missing: {unresolved[:10]}{'...' if len(unresolved) > 10 else ''}",
)

# Per-recipe more detailed check (for diagnostics)
broken_recipes = []
for r in recipes:
    for slot in r.get("ingredients", []) + r.get("results", []):
        n = slot["name"]
        t = slot.get("type", "item")
        if t == "fluid" and n not in fluid_names:
            broken_recipes.append((r["name"], "fluid", n))
        elif t == "item" and n not in item_names:
            broken_recipes.append((r["name"], "item", n))
check(
    "no recipe references an item under a fluid type or vice versa",
    not broken_recipes,
    f"first 5: {broken_recipes[:5]}",
)

# -----------------------------------------------------------------------------
# 2. Every recipe category has at least one machine
# -----------------------------------------------------------------------------
section("recipe categories have crafters")
craft_cats = recipe_categories["crafting_categories"]
res_cats = recipe_categories["resource_categories"]

# `parameters` is a synthetic category used only by parametrized-blueprint
# placeholder recipes (`parameter-0`, `parameter-1`, ...) and intentionally
# has no real machine. It's not a data bug.
SYNTHETIC_RECIPE_CATEGORIES = {"parameters"}

orphan_categories = []
for cat in sorted({r["category"] for r in recipes}):
    if cat in SYNTHETIC_RECIPE_CATEGORIES:
        continue
    candidates = craft_cats.get(cat, [])
    if not candidates:
        orphan_categories.append(cat)
check(
    "every non-synthetic recipe category has at least one machine",
    not orphan_categories,
    f"orphans: {orphan_categories}",
)

# Every machine listed in a category actually exists
unknown_machines_in_cats = []
for cat, ms in craft_cats.items():
    for m in ms:
        if m not in machine_names:
            unknown_machines_in_cats.append((cat, m))
for cat, ms in res_cats.items():
    for m in ms:
        if m not in machine_names:
            unknown_machines_in_cats.append((cat, m))
check(
    "category->machine table only references known machines",
    not unknown_machines_in_cats,
    f"first 5: {unknown_machines_in_cats[:5]}",
)

# -----------------------------------------------------------------------------
# 3. entity_planet_restrictions entries exist somewhere
# -----------------------------------------------------------------------------
section("entity_planet_restrictions cross-reference")
unknown_restrictions = []
for name, info in entity_planet_restrictions.items():
    typ = info.get("type")
    if typ == "recipe":
        if name not in recipe_names:
            unknown_restrictions.append((name, typ, "missing in recipes.json"))
    else:
        # Anything that isn't a recipe should be findable in some entity-like
        # spec (machine, beacon, belt, inserter, robot, electric, container...)
        # Containers, locomotives, rails etc. are not in our specs - they are
        # in items.json (since the placed item carries the prototype name).
        if name not in all_entity_like and name not in item_names:
            unknown_restrictions.append((name, typ, "no spec entry"))
check(
    "every entity_planet_restrictions entry resolves to a known prototype",
    not unknown_restrictions,
    f"first 5: {unknown_restrictions[:5]}",
)

# -----------------------------------------------------------------------------
# 4. Recipe-targeted research effects point to real recipes
# -----------------------------------------------------------------------------
section("research effects -> recipe references")
unknown_recipe_refs = []
for r in research_effects:
    rec = r.get("recipe")
    if rec is not None and rec not in recipe_names:
        unknown_recipe_refs.append((r.get("tech_name"), r.get("effect_type"), rec))
check(
    "every research effect's recipe field is a known recipe",
    not unknown_recipe_refs,
    f"first 5: {unknown_recipe_refs[:5]}",
)

# -----------------------------------------------------------------------------
# 5. Belt math: speed * 60 * 8 * 2 == items_per_second_total
# -----------------------------------------------------------------------------
section("belt math")
belt_math_failures = []
for b in belts:
    if b.get("type") != "transport-belt":
        continue
    spd = b["speed_tiles_per_tick"]
    expected_total = spd * 60 * 8 * 2
    actual_total = b["items_per_second_total"]
    if not math.isclose(expected_total, actual_total, rel_tol=1e-6, abs_tol=1e-6):
        belt_math_failures.append((b["name"], expected_total, actual_total))
check(
    "speed*60*8*2 == items_per_second_total for every transport belt",
    not belt_math_failures,
    f"first 5: {belt_math_failures[:5]}",
)

# Also: per-lane half of total
per_lane_failures = []
for b in belts:
    if b.get("type") != "transport-belt":
        continue
    if not math.isclose(b["items_per_second_per_lane"] * 2, b["items_per_second_total"]):
        per_lane_failures.append(b["name"])
check(
    "items_per_second_per_lane * 2 == items_per_second_total",
    not per_lane_failures,
    f"first 5: {per_lane_failures[:5]}",
)

# -----------------------------------------------------------------------------
# 6. Inserter quarter-turn time == 0.25 / rotation_speed
# -----------------------------------------------------------------------------
section("inserter rotation math")
inserter_failures = []
for ins in inserters:
    rot = ins["rotation_speed_rev_per_tick"]
    expected = 0.25 / rot
    actual = ins["quarter_turn_ticks"]
    if not math.isclose(expected, actual, rel_tol=1e-3, abs_tol=1e-3):
        inserter_failures.append((ins["name"], expected, actual))
check(
    "quarter_turn_ticks == 0.25 / rotation_speed for every inserter",
    not inserter_failures,
    f"first 5: {inserter_failures[:5]}",
)

# -----------------------------------------------------------------------------
# 7. Planets have all 5 surface properties (real planets only, not space-locations)
# -----------------------------------------------------------------------------
section("planet surface properties")
required_props = {"gravity", "pressure", "magnetic-field", "solar-power", "day-night-cycle"}
missing_props = []
for p in planets:
    if p.get("type") != "planet":
        continue  # space-location and the platform pseudo-surface skip
    sp = p.get("surface_properties", {})
    missing = required_props - set(sp.keys())
    if missing:
        missing_props.append((p["name"], sorted(missing)))
check(
    "every planet exposes all 5 surface properties",
    not missing_props,
    f"first 5: {missing_props[:5]}",
)

# Surfaces (non-planet, non-space-location) should also expose the 5 props
# (the space-platform pseudo-surface in this dump does)
for p in planets:
    if p.get("type") == "surface":
        sp = p.get("surface_properties", {})
        missing = required_props - set(sp.keys())
        check(
            f"surface {p['name']} exposes all 5 surface properties",
            not missing,
            f"missing: {sorted(missing)}",
        )

# -----------------------------------------------------------------------------
# 8. Quality tier monotonicity
# -----------------------------------------------------------------------------
section("quality tier ordering")
ranked = sorted(quality, key=lambda q: q["rank"])
check(
    "quality ranks are 0..N-1 contiguous",
    [q["rank"] for q in ranked] == list(range(len(ranked))),
    f"got {[q['rank'] for q in ranked]}",
)

# Speed multiplier monotone non-decreasing
speed_mults = [q["machine_speed_multiplier"] for q in ranked]
check(
    "machine_speed_multiplier non-decreasing across quality tiers",
    all(a <= b for a, b in zip(speed_mults, speed_mults[1:])),
    f"got {speed_mults}",
)

# Beacon power usage multiplier monotone non-increasing (better quality => less power)
bpwr = [q["beacon_power_usage_multiplier"] for q in ranked]
check(
    "beacon_power_usage_multiplier non-increasing across quality tiers",
    all(a >= b for a, b in zip(bpwr, bpwr[1:])),
    f"got {bpwr}",
)

# -----------------------------------------------------------------------------
# 9. Beacon profile sanity: profile[0] == 1.0
# -----------------------------------------------------------------------------
section("beacon profile sanity")
for b in beacons:
    profile = b.get("profile", [])
    check(
        f"beacon {b['name']} profile[0] == 1.0",
        len(profile) > 0 and math.isclose(profile[0], 1.0, abs_tol=1e-6),
        f"got profile[0]={profile[0] if profile else None!r}",
    )

# Profile length matches profile_length
for b in beacons:
    if b.get("profile_length") is not None:
        check(
            f"beacon {b['name']} profile length matches profile_length",
            len(b["profile"]) == b["profile_length"],
            f"profile len={len(b['profile'])} vs profile_length={b['profile_length']}",
        )

# -----------------------------------------------------------------------------
# 10. Module effects are within plausible bounds
# -----------------------------------------------------------------------------
section("module effect bounds")
for m in modules:
    eff = m["effect"]
    # speed module quality penalty must be negative
    if "speed" in eff and m["category"] == "speed":
        check(
            f"speed module {m['name']} has positive speed effect",
            eff["speed"] > 0,
            f"got {eff['speed']}",
        )
    if "productivity" in eff and m["category"] == "productivity" and m["tier"] in (1, 2, 3):
        # vanilla productivity-module-3 = +0.1
        check(
            f"productivity module {m['name']} productivity in (0, 0.5]",
            0 < eff["productivity"] <= 0.5,
            f"got {eff['productivity']}",
        )

# -----------------------------------------------------------------------------
# 11. Crafting machines have a non-empty crafting_categories list
# -----------------------------------------------------------------------------
section("crafting machines have categories")
for m in machines:
    if m.get("type") in {"assembling-machine", "furnace", "rocket-silo"}:
        check(
            f"machine {m['name']} has crafting_categories",
            bool(m.get("crafting_categories")),
            f"got {m.get('crafting_categories')}",
        )

# Mining drills have resource_categories
section("mining drills have resource_categories")
mining_with_cats = [m for m in machines if m.get("type") == "mining-drill"]
for m in mining_with_cats:
    # the spec carries crafting_categories empty for drills; resource cats live in recipe_categories.json
    drill_cats = [c for c, ds in res_cats.items() if m["name"] in ds]
    check(
        f"mining drill {m['name']} appears in some resource_category",
        bool(drill_cats),
        f"name not in any resource_categories key",
    )

# -----------------------------------------------------------------------------
# 12. Vanilla baseline annotation sanity
# -----------------------------------------------------------------------------
section("vanilla baseline annotations")
# beacon entry must carry vanilla_2_0_76 since dumped beacon is modded
beacon_entry = next((b for b in beacons if b["name"] == "beacon"), None)
check(
    "beacon entry has vanilla_2_0_76 annotation",
    beacon_entry is not None and "vanilla_2_0_76" in beacon_entry,
)

# logistic-robot in robots.json must carry vanilla_2_0_76
logistic = next((r for r in robots["robots"] if r["name"] == "logistic-robot"), None)
check(
    "logistic-robot entry has vanilla_2_0_76 annotation",
    logistic is not None and "vanilla_2_0_76" in logistic,
)

# foundry must carry vanilla annotation (its base productivity differs)
foundry = next((m for m in machines if m["name"] == "foundry"), None)
check(
    "foundry entry has vanilla_2_0_76 annotation",
    foundry is not None and "vanilla_2_0_76" in foundry,
)

# -----------------------------------------------------------------------------
# 13. Recipe planet restrictions reference real planets
# -----------------------------------------------------------------------------
section("recipe planet restrictions")
for name, info in recipe_planet_restrictions.items():
    if name not in recipe_names:
        check(f"recipe planet restriction {name} is a real recipe", False)
    for p in info.get("allowed_planets", []):
        check(
            f"recipe {name} allowed_planets entry {p} is a known planet/surface",
            p in planet_names,
        )

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
print()
print(f"PASS: {PASS}")
print(f"FAIL: {FAIL}")
if FAILURES:
    print("\nFailures:")
    for f in FAILURES:
        print(f"  {f}")
sys.exit(0 if FAIL == 0 else 1)
