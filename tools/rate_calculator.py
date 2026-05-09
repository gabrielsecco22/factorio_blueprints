"""Install-aware Factorio rate calculator.

Pure-Python, stdlib-only engine that consumes the curated catalogs in
`specs/*.json` and reports inputs/outputs/power/pollution for any single
machine recipe + module + beacon + research configuration.

Public API
----------

    from tools.rate_calculator import (
        RateInput, Beacon, RateOutput, compute_rates,
    )

The math mirrors the in-game `RateCalculator` mod by raiguard
(specifically `process_crafter` in `scripts/calc-util.lua`), with three
documented extensions:

    1. Per-recipe productivity research (`change-recipe-productivity`).
       The mod reads it implicitly off the recipe object; we accept the
       level explicitly via `RateInput.research_levels`.
    2. Quality cascade odds. The mod surfaces only the per-craft chance;
       we compute the full output distribution.
    3. Modded beacons (multi-slot, productivity-allowed, etc.). The
       Space Age beacon profile is `1/sqrt(N)` -- we honour the data,
       not any hard-coded formula.

All clamps are reported as strings on `RateOutput.diagnostics`. The
caller can show them to the user.

Engine constants
----------------

    SPEED_FLOOR = 0.2          machine speed clamp (Factorio engine)
    QUALITY_CAP = 0.248        per-craft quality upgrade chance
    PROD_CAP_DEFAULT = 3.0     +300% productivity (overridable per-recipe
                                via `recipe.maximum_productivity`)

These constants are taken from the 2.0 engine source as cited in the
Factorio Wiki (https://wiki.factorio.com/Modules) and verified against
the RateCalculator mod's `recipe.prototype.maximum_productivity` reads.
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Union

# ---------------------------------------------------------------------------
# Engine constants
# ---------------------------------------------------------------------------

SPEED_FLOOR: float = 0.2
QUALITY_CAP: float = 0.248
PROD_CAP_DEFAULT: float = 3.0  # +300%

# Module effect keys we know about.
EFFECT_KEYS = ("speed", "productivity", "consumption", "pollution", "quality")


# ---------------------------------------------------------------------------
# Catalog loader
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "specs"


def _load_list_by_name(filename: str) -> dict[str, dict[str, Any]]:
    data = json.loads((SPECS_DIR / filename).read_text())
    return {it["name"]: it for it in data}


_CACHE: dict[str, Any] = {}


def _catalog(filename: str) -> dict[str, dict[str, Any]]:
    if filename not in _CACHE:
        _CACHE[filename] = _load_list_by_name(filename)
    return _CACHE[filename]


def recipes_catalog() -> dict[str, dict[str, Any]]:
    return _catalog("recipes.json")


def machines_catalog() -> dict[str, dict[str, Any]]:
    return _catalog("machines.json")


def modules_catalog() -> dict[str, dict[str, Any]]:
    return _catalog("modules.json")


def beacons_catalog() -> dict[str, dict[str, Any]]:
    return _catalog("beacons.json")


def quality_catalog() -> dict[str, dict[str, Any]]:
    return _catalog("quality.json")


def belts_catalog() -> dict[str, dict[str, Any]]:
    return _catalog("belts.json")


def research_effects_list() -> list[dict[str, Any]]:
    if "research_effects.json" not in _CACHE:
        _CACHE["research_effects.json"] = json.loads(
            (SPECS_DIR / "research_effects.json").read_text()
        )
    return _CACHE["research_effects.json"]


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

ModuleSpec = tuple[str, str]  # (module_name, quality_name)


@dataclass
class Beacon:
    """One beacon (or row of identical beacons) covering the target machine."""

    name: str = "beacon"
    quality: str = "normal"
    count: int = 1  # number of beacons of this group covering the machine
    modules: list[ModuleSpec] = field(default_factory=list)


@dataclass
class RateInput:
    """Single-recipe production query.

    Required: `recipe`, `machine`. Everything else has a sensible default.
    """

    recipe: str
    machine: str
    machine_quality: str = "normal"
    modules: list[ModuleSpec] = field(default_factory=list)
    beacons: list[Beacon] = field(default_factory=list)
    research_levels: dict[str, Any] = field(default_factory=dict)
    machine_count: int = 1

    # Toggle modded vs vanilla baseline (overlay `vanilla_2_0_76` if present).
    use_modded: bool = True

    # Engine constants (configurable for mods that change them).
    productivity_cap: float = PROD_CAP_DEFAULT
    speed_floor: float = SPEED_FLOOR
    quality_cap: float = QUALITY_CAP


@dataclass
class RateOutput:
    """Result of a `compute_rates` call."""

    # Effect aggregates (additive, in module-effect space).
    raw_speed_bonus: float = 0.0
    raw_productivity_bonus: float = 0.0
    raw_consumption_bonus: float = 0.0
    raw_pollution_bonus: float = 0.0
    raw_quality_bonus: float = 0.0

    # Effective multipliers actually used in throughput math.
    effective_speed_multiplier: float = 1.0  # post-floor (1 + bonus)
    effective_productivity: float = 0.0  # additive (e.g. 0.5 = +50%)
    effective_consumption_multiplier: float = 1.0
    effective_pollution_multiplier: float = 1.0
    effective_quality_chance: float = 0.0  # per-craft cascade chance
    machine_speed: float = 0.0  # post-quality machine-base
    crafting_speed_multiplier: float = 1.0  # post-floor (1 + bonus)

    # Throughput.
    crafts_per_second_per_machine: float = 0.0
    crafts_per_second_total: float = 0.0
    inputs_per_second: dict[str, float] = field(default_factory=dict)
    outputs_per_second: dict[str, float] = field(default_factory=dict)
    outputs_by_quality_per_second: dict[str, dict[str, float]] = field(default_factory=dict)

    # Power and pollution.
    power_kw_per_machine: float = 0.0
    power_kw_total: float = 0.0
    beacon_power_kw_total: float = 0.0
    pollution_per_minute_per_machine: float = 0.0
    pollution_per_minute_total: float = 0.0

    # Diagnostics.
    diagnostics: list[str] = field(default_factory=list)

    # Echo of inputs for downstream reporting.
    recipe: str = ""
    machine: str = ""
    machine_quality: str = "normal"
    machine_count: int = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _machine_overlay(machine: dict, use_modded: bool) -> dict:
    """Apply the `vanilla_2_0_76` overlay unless `use_modded` is True."""
    if use_modded or "vanilla_2_0_76" not in machine:
        return machine
    overlaid = dict(machine)
    overlaid.update(machine["vanilla_2_0_76"])
    return overlaid


def _beacon_overlay(beacon: dict, use_modded: bool) -> dict:
    if use_modded or "vanilla_2_0_76" not in beacon:
        return beacon
    overlaid = dict(beacon)
    overlaid.update(beacon["vanilla_2_0_76"])
    return overlaid


def _qfact(name: str, key: str = "module_effect_multiplier") -> float:
    """Quality multiplier for a module/beacon/machine effect."""
    qcat = quality_catalog()
    if name not in qcat:
        raise ValueError(f"unknown quality tier {name!r}")
    return float(qcat[name][key])


def _module_effect(module_name: str, module_quality: str, diags: list[str]) -> dict[str, float]:
    """Return a `dict[effect -> bonus]` for one module at given quality."""
    mods = modules_catalog()
    if module_name not in mods:
        raise ValueError(f"unknown module {module_name!r}")
    m = mods[module_name]
    base = dict(m["effect"] or {})
    qmult = _qfact(module_quality, "module_effect_multiplier")
    out: dict[str, float] = {}
    for k in EFFECT_KEYS:
        v = float(base.get(k, 0.0))
        if v == 0.0:
            continue
        # Quality multiplier amplifies positive effects but not penalties.
        # In Factorio 2.0, ALL effect components scale with the module's
        # quality multiplier (positive AND negative -- both speed bonus
        # and the consumption penalty grow). RateCalculator mod doesn't
        # break this out explicitly because it queries the engine, but
        # the wiki and the dump confirm it.
        out[k] = v * qmult
    return out


def _beacon_distribution(
    beacon: dict, beacon_quality: str, n_same_type: int, diags: list[str]
) -> float:
    """Return effective per-module multiplier supplied by ONE beacon of this kind.

    For Factorio 2.0 / Space Age:
        effectivity = beacon.distribution_effectivity
                      + n_quality_levels * distribution_effectivity_bonus_per_quality_level
        per_module_share = effectivity * profile[N-1]
    where N = number of beacons of this same-type counter affecting the machine.
    The same-type counter is what the engine uses; we approximate that as
    "number of beacons of this beacon prototype covering the machine".
    """
    eff_base = float(beacon["distribution_effectivity"])
    bonus_per = float(beacon.get("distribution_effectivity_bonus_per_quality_level", 0.0) or 0.0)
    qcat = quality_catalog()
    qlevel = int(qcat[beacon_quality]["level"])
    eff = eff_base + bonus_per * qlevel

    profile = beacon.get("profile") or [1.0]
    if not profile:
        diags.append(f"beacon {beacon['name']!r}: empty profile, defaulting to 1.0")
        profile = [1.0]
    idx = max(0, min(n_same_type - 1, len(profile) - 1))
    if n_same_type < 1:
        diags.append(
            f"beacon {beacon['name']!r}: count<1 (got {n_same_type}); using profile[0]"
        )
        idx = 0
    return eff * float(profile[idx])


def _aggregate_module_effects(
    modules: Iterable[ModuleSpec], diags: list[str]
) -> dict[str, float]:
    total = {k: 0.0 for k in EFFECT_KEYS}
    for mod_name, mod_q in modules:
        eff = _module_effect(mod_name, mod_q, diags)
        for k, v in eff.items():
            total[k] += v
    return total


def _filter_disallowed_effects(
    effects: dict[str, float],
    allowed: Optional[Iterable[str]],
    label: str,
    diags: list[str],
) -> dict[str, float]:
    """Zero out any effect not in `allowed`, recording a diagnostic.

    Important note (matches engine + RateCalculator): when productivity
    modules are in a machine that disallows productivity, only the
    productivity component is dropped -- the speed/consumption/pollution
    PENALTIES still apply. We model this by zeroing only the disallowed
    keys in `effects`, not the modules wholesale.
    """
    if allowed is None:
        return effects
    allowed_set = set(allowed)
    filtered = dict(effects)
    for k in EFFECT_KEYS:
        if k not in allowed_set and filtered.get(k):
            diags.append(
                f"{label}: effect {k!r} not allowed; zeroed (was {filtered[k]:+.4f})"
            )
            filtered[k] = 0.0
    return filtered


def _resolve_recipe_productivity_research(
    recipe_name: str, levels: dict[str, Any]
) -> float:
    """Sum `change-recipe-productivity` effects for `recipe_name`.

    `levels["change-recipe-productivity"]` may be:
        - a flat int/float: applied to every matching tech that targets `recipe_name`.
        - a dict {recipe -> level}: per-recipe lookup.
    """
    raw = levels.get("change-recipe-productivity")
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        # Flat: count techs whose recipe == recipe_name and apply once.
        # (Multiple techs targeting the same recipe stack additively.)
        total = 0.0
        for r in research_effects_list():
            if r.get("effect_type") != "change-recipe-productivity":
                continue
            if r.get("recipe") != recipe_name:
                continue
            modifier = float(r.get("modifier", 0.1))
            total += modifier * float(raw)
        return total
    if isinstance(raw, dict):
        total = 0.0
        # raw is keyed by tech_name OR recipe_name. We accept both.
        for key, lvl in raw.items():
            if not isinstance(lvl, (int, float)):
                continue
            for r in research_effects_list():
                if r.get("effect_type") != "change-recipe-productivity":
                    continue
                # match by tech name OR recipe name
                if r.get("tech_name") != key and r.get("recipe") != key:
                    continue
                if r.get("recipe") != recipe_name:
                    continue
                modifier = float(r.get("modifier", 0.1))
                total += modifier * float(lvl)
        return total
    return 0.0


def _quality_cascade(
    base_amount: float, chance: float, source_quality: str, max_steps: int = 4
) -> dict[str, float]:
    """Distribute `base_amount` of items across the quality cascade.

    For each item produced, with probability `chance` it upgrades one
    tier. The upgrade itself may upgrade again with probability 0.1
    (the standard Factorio quality cascade). We model the geometric
    series with a small loop (max 4 hops).
    """
    qcat = quality_catalog()
    # Build ordered list of tiers by rank.
    tiers = sorted(qcat.values(), key=lambda q: q["rank"])
    name_to_idx = {q["name"]: q["rank"] for q in tiers}
    max_rank = max(name_to_idx.values())

    if source_quality not in name_to_idx:
        raise ValueError(f"unknown source quality {source_quality!r}")
    src_rank = name_to_idx[source_quality]
    out: dict[str, float] = {}

    if chance <= 0:
        out[source_quality] = base_amount
        return out

    # Probability vector across ranks starting at src_rank.
    # p[0] is "stays at source"; p[k] for k>=1 is "ends k tiers up".
    # Engine: with one cascade chance c, prob of upgrading = c, then
    # sub-cascade probability = 0.1 each subsequent step. Compute up to
    # max_steps levels of cascade.
    SUBCASCADE = 0.1
    probs: list[float] = [1.0 - chance]
    remaining = chance
    for k in range(1, max_steps + 1):
        if k == max_steps:
            probs.append(remaining)
        else:
            stay = remaining * (1.0 - SUBCASCADE)
            probs.append(stay)
            remaining = remaining * SUBCASCADE

    # Map ranks to quality names by rank.
    rank_to_name = {q["rank"]: q["name"] for q in tiers}
    for k, p in enumerate(probs):
        target_rank = min(src_rank + k, max_rank)
        qname = rank_to_name[target_rank]
        out[qname] = out.get(qname, 0.0) + base_amount * p
    return out


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


def compute_rates(inp: RateInput) -> RateOutput:
    """Compute throughput / power / pollution / quality for one production cell."""
    out = RateOutput(
        recipe=inp.recipe,
        machine=inp.machine,
        machine_quality=inp.machine_quality,
        machine_count=inp.machine_count,
    )
    diags = out.diagnostics

    # -- Resolve catalog rows ------------------------------------------------
    recs = recipes_catalog()
    if inp.recipe not in recs:
        raise ValueError(f"unknown recipe {inp.recipe!r}")
    recipe = recs[inp.recipe]

    machines = machines_catalog()
    if inp.machine not in machines:
        raise ValueError(f"unknown machine {inp.machine!r}")
    machine = _machine_overlay(machines[inp.machine], inp.use_modded)

    if inp.machine_count <= 0:
        diags.append(f"machine_count={inp.machine_count} <= 0; treated as 1 for per-machine math")

    # -- Validate module slots ----------------------------------------------
    machine_slots = int(machine.get("module_slots") or 0)
    if len(inp.modules) > machine_slots:
        diags.append(
            f"too many modules: {len(inp.modules)} provided, machine has {machine_slots} slots; "
            f"truncating"
        )
        inp_modules = inp.modules[:machine_slots]
    else:
        inp_modules = list(inp.modules)

    # -- Validate productivity allowance for the recipe ---------------------
    allow_productivity = bool(recipe.get("allow_productivity", True))
    allow_quality = bool(recipe.get("allow_quality", True))

    # -- Aggregate module effects -------------------------------------------
    machine_module_eff = _aggregate_module_effects(inp_modules, diags)

    # Filter by machine-allowed effects (productivity may be forbidden).
    machine_module_eff = _filter_disallowed_effects(
        machine_module_eff,
        machine.get("allowed_effects"),
        f"machine {inp.machine!r}",
        diags,
    )
    # And by recipe allowance (e.g. allow_productivity=False).
    if not allow_productivity and machine_module_eff.get("productivity"):
        diags.append(
            f"recipe {inp.recipe!r}: allow_productivity=false; productivity component zeroed"
        )
        machine_module_eff["productivity"] = 0.0
    if not allow_quality and machine_module_eff.get("quality"):
        diags.append(
            f"recipe {inp.recipe!r}: allow_quality=false; quality component zeroed"
        )
        machine_module_eff["quality"] = 0.0

    # -- Beacon contributions ------------------------------------------------
    beacons_cat = beacons_catalog()
    beacon_eff_total = {k: 0.0 for k in EFFECT_KEYS}
    beacon_power_total_kw = 0.0
    qcat = quality_catalog()
    for bcfg in inp.beacons:
        if bcfg.name not in beacons_cat:
            diags.append(f"unknown beacon {bcfg.name!r}; skipped")
            continue
        beacon_proto = _beacon_overlay(beacons_cat[bcfg.name], inp.use_modded)
        bslots = int(beacon_proto.get("module_slots") or 0)
        bmods = list(bcfg.modules)
        if len(bmods) > bslots:
            diags.append(
                f"beacon {bcfg.name!r}: too many modules ({len(bmods)} vs {bslots} slots); truncating"
            )
            bmods = bmods[:bslots]

        # Aggregate the modules in ONE beacon.
        per_beacon_module_eff = _aggregate_module_effects(bmods, diags)
        # Filter against beacon's allowed_effects.
        per_beacon_module_eff = _filter_disallowed_effects(
            per_beacon_module_eff,
            beacon_proto.get("allowed_effects"),
            f"beacon {bcfg.name!r}",
            diags,
        )

        # Distribute via beacon profile.
        # Same-type count = bcfg.count (caller's responsibility to group).
        per_module_share = _beacon_distribution(beacon_proto, bcfg.quality, bcfg.count, diags)
        # Quality scaling on the beacon strength itself (Space Age).
        beacon_strength_q = float(qcat[bcfg.quality]["beacon_strength_multiplier"])

        # Each beacon contributes per_module_share * (sum of module effects).
        # Cap modules' effects against machine's allowed_effects too.
        for k in EFFECT_KEYS:
            v = per_beacon_module_eff.get(k, 0.0)
            if v == 0.0:
                continue
            if machine.get("allowed_effects") is not None and k not in set(
                machine["allowed_effects"]
            ):
                diags.append(
                    f"beacon {bcfg.name!r}: machine forbids {k!r}; beacon contribution zeroed"
                )
                continue
            if k == "productivity" and not allow_productivity:
                diags.append(
                    f"beacon {bcfg.name!r}: recipe disallows productivity; component zeroed"
                )
                continue
            if k == "quality" and not allow_quality:
                continue
            beacon_eff_total[k] += per_module_share * v * bcfg.count * beacon_strength_q

        # Beacon's own base_effect.productivity (e.g. modded multi-prod beacon).
        beacon_base = (beacon_proto.get("effect_receiver") or {}).get("base_effect") or {}
        for k, v in beacon_base.items():
            if k not in EFFECT_KEYS or not v:
                continue
            if machine.get("allowed_effects") is not None and k not in set(
                machine["allowed_effects"]
            ):
                continue
            if k == "productivity" and not allow_productivity:
                continue
            beacon_eff_total[k] += per_module_share * float(v) * bcfg.count * beacon_strength_q

        # Beacon power (per beacon).
        per_beacon_power = float(beacon_proto.get("energy_usage_kw") or 0.0)
        bpu_q = float(qcat[bcfg.quality]["beacon_power_usage_multiplier"])
        beacon_power_total_kw += per_beacon_power * bpu_q * bcfg.count

    # -- base_effect from machine prototype (e.g. foundry +50% prod) --------
    machine_base_effect = dict(machine.get("base_effect") or {})
    if not allow_productivity and machine_base_effect.get("productivity"):
        diags.append(
            f"machine {inp.machine!r}: base_effect.productivity present but recipe disallows; zeroed"
        )
        machine_base_effect["productivity"] = 0.0

    # -- Per-recipe productivity research ----------------------------------
    research_recipe_prod = _resolve_recipe_productivity_research(
        inp.recipe, inp.research_levels
    )
    if research_recipe_prod and not allow_productivity:
        diags.append(
            f"recipe {inp.recipe!r}: research productivity present but recipe disallows; zeroed"
        )
        research_recipe_prod = 0.0

    # -- Sum into raw bonuses ----------------------------------------------
    raw_speed = machine_module_eff.get("speed", 0.0) + beacon_eff_total["speed"]
    raw_prod = (
        machine_module_eff.get("productivity", 0.0)
        + beacon_eff_total["productivity"]
        + float(machine_base_effect.get("productivity", 0.0))
        + research_recipe_prod
    )
    raw_cons = machine_module_eff.get("consumption", 0.0) + beacon_eff_total["consumption"]
    raw_poll = machine_module_eff.get("pollution", 0.0) + beacon_eff_total["pollution"]
    raw_qual = machine_module_eff.get("quality", 0.0) + beacon_eff_total["quality"]

    out.raw_speed_bonus = raw_speed
    out.raw_productivity_bonus = raw_prod
    out.raw_consumption_bonus = raw_cons
    out.raw_pollution_bonus = raw_poll
    out.raw_quality_bonus = raw_qual

    # -- Apply caps and floors ---------------------------------------------
    speed_mult = 1.0 + raw_speed
    if speed_mult < inp.speed_floor:
        diags.append(
            f"speed multiplier {speed_mult:.3f} below floor {inp.speed_floor}; "
            f"clamped to {inp.speed_floor}"
        )
        speed_mult = inp.speed_floor

    # Productivity: per-recipe override beats global default.
    recipe_max_prod = recipe.get("maximum_productivity")
    if recipe_max_prod is None:
        prod_cap = inp.productivity_cap
    else:
        prod_cap = float(recipe_max_prod)
    if raw_prod > prod_cap:
        diags.append(
            f"productivity bonus {raw_prod:+.3f} above cap {prod_cap:+.3f}; clamped"
        )
        prod = prod_cap
    else:
        prod = max(0.0, raw_prod)

    # Consumption: floor at 0.2 (matches in-game module display) -- the
    # engine clamps consumption multiplier at 0.2.
    cons_mult = 1.0 + raw_cons
    if cons_mult < 0.2:
        diags.append(
            f"consumption multiplier {cons_mult:.3f} below floor 0.2; clamped"
        )
        cons_mult = 0.2

    pollution_mult = max(0.0, 1.0 + raw_poll)

    # Quality cascade chance.
    quality_chance = max(0.0, raw_qual)
    if quality_chance > inp.quality_cap:
        diags.append(
            f"quality chance {quality_chance:.4f} above cap {inp.quality_cap}; clamped"
        )
        quality_chance = inp.quality_cap

    out.effective_speed_multiplier = speed_mult
    out.crafting_speed_multiplier = speed_mult  # alias
    out.effective_productivity = prod
    out.effective_consumption_multiplier = cons_mult
    out.effective_pollution_multiplier = pollution_mult
    out.effective_quality_chance = quality_chance

    # -- Crafting throughput ------------------------------------------------
    base_speed = float(machine.get("crafting_speed", 0.0))
    machine_q_mult = float(qcat[inp.machine_quality]["machine_speed_multiplier"])
    machine_speed = base_speed * machine_q_mult
    out.machine_speed = machine_speed

    energy_required = float(recipe.get("energy_required", 1.0))
    if energy_required <= 0:
        raise ValueError(f"recipe {inp.recipe!r} has non-positive energy_required={energy_required}")

    # crafts/s = (machine_speed * speed_mult) / energy_required
    crafts_per_sec = (machine_speed * speed_mult) / energy_required
    out.crafts_per_second_per_machine = crafts_per_sec
    n = max(1, inp.machine_count)
    out.crafts_per_second_total = crafts_per_sec * n

    # -- Inputs and outputs -------------------------------------------------
    inputs: dict[str, float] = {}
    for ing in recipe.get("ingredients", []) or []:
        nm = ing["name"]
        amt = float(ing["amount"])
        # Productivity does not affect ingredient consumption.
        per_sec = crafts_per_sec * amt * n
        inputs[nm] = inputs.get(nm, 0.0) + per_sec
    out.inputs_per_second = inputs

    outputs: dict[str, float] = {}
    outputs_by_q: dict[str, dict[str, float]] = {}
    for prod_slot in recipe.get("results", []) or []:
        nm = prod_slot["name"]
        ptype = prod_slot.get("type", "item")
        amt_raw = prod_slot.get("amount")
        amt_min = prod_slot.get("amount_min")
        amt_max = prod_slot.get("amount_max")
        prob = float(prod_slot.get("probability", 1.0) or 1.0)
        ignored_by_prod = float(prod_slot.get("ignored_by_productivity", 0.0) or 0.0)
        extra_count_fraction = float(prod_slot.get("extra_count_fraction", 0.0) or 0.0)

        if amt_raw is not None:
            avg = float(amt_raw)
        else:
            avg = (float(amt_min or 0.0) + float(amt_max or 0.0)) / 2.0
        expected = prob * avg + extra_count_fraction
        # Productivity only multiplies the part beyond `ignored_by_productivity`.
        prod_complement = min(expected, ignored_by_prod)
        prod_base = expected - prod_complement
        amount_per_craft = prod_complement + prod_base * (1.0 + prod)
        per_sec = crafts_per_sec * amount_per_craft * n
        outputs[nm] = outputs.get(nm, 0.0) + per_sec

        # Quality cascade (items only, only when chance > 0).
        if ptype == "item" and quality_chance > 0 and allow_quality:
            cascade = _quality_cascade(per_sec, quality_chance, inp.machine_quality)
            qmap = outputs_by_q.setdefault(nm, {})
            for q, v in cascade.items():
                qmap[q] = qmap.get(q, 0.0) + v
        else:
            qmap = outputs_by_q.setdefault(nm, {})
            qmap[inp.machine_quality] = qmap.get(inp.machine_quality, 0.0) + per_sec

    out.outputs_per_second = outputs
    out.outputs_by_quality_per_second = outputs_by_q

    # -- Power --------------------------------------------------------------
    energy_use_kw = float(machine.get("energy_usage_kw") or 0.0)
    drain_kw = float(machine.get("drain_kw") or 0.0)
    per_machine_power = energy_use_kw * cons_mult + drain_kw
    out.power_kw_per_machine = per_machine_power
    out.power_kw_total = per_machine_power * n + beacon_power_total_kw
    out.beacon_power_kw_total = beacon_power_total_kw

    # -- Pollution ----------------------------------------------------------
    base_pollution = float(machine.get("pollution") or 0.0)  # per-minute
    # Engine: pollution = base * pollution_mult * speed_mult * cons_mult
    # (the speed factor comes from "while crafting"; in our steady-state
    # model the machine is always crafting, so multiplying by speed_mult
    # is correct. cons_mult is included to track the consumption-modifier's
    # effect on emissions, matching the wiki.)
    pol_per_min = base_pollution * pollution_mult * speed_mult * cons_mult
    out.pollution_per_minute_per_machine = pol_per_min
    out.pollution_per_minute_total = pol_per_min * n

    return out


# ---------------------------------------------------------------------------
# Convenience: belt saturation
# ---------------------------------------------------------------------------


def belt_saturation(item_per_sec: float, belt_name: str) -> dict[str, float]:
    """Return how many belts (and lanes) of `belt_name` are saturated."""
    belts = belts_catalog()
    if belt_name not in belts:
        raise ValueError(f"unknown belt {belt_name!r}")
    b = belts[belt_name]
    belt_total = float(b["items_per_second_total"])
    belt_lane = float(b["items_per_second_per_lane"])
    return {
        "belt_full_belts": item_per_sec / belt_total if belt_total > 0 else float("inf"),
        "belt_lanes": item_per_sec / belt_lane if belt_lane > 0 else float("inf"),
        "items_per_second": item_per_sec,
        "belt_capacity_per_sec": belt_total,
    }
