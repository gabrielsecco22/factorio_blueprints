#!/usr/bin/env python3
"""Pattern-match a decoded blueprint to a short purpose string.

Stdlib only. Intended to be called from
``tools/inventory_user_blueprints.py`` to label each blueprint in a
user's library with a one-line "purpose guess" they can confirm or
correct.

Public API
----------

    from blueprint_classifier import classify, Classification

    cls = classify(decoded_blueprint)
    print(cls.label, cls.confidence)

`classify` accepts a decoded blueprint object (the dict returned by
``blueprint_codec.decode``) for either a plain blueprint
(``{"blueprint": {...}}``) or a blueprint book
(``{"blueprint_book": {...}}``). For books it classifies the *aggregate*
of all entities across all child blueprints (you usually want to call
``classify`` per-child for a richer picture; this tool just returns one
label).

The heuristic is conservative:

    1. Strong single-entity tells (rocket-silo, foundry, recycler,
       etc.) win immediately and produce a high-confidence label.
    2. Combined-tells (solar-panel + accumulator, oil-refinery +
       chemical-plant, mining-drill + electric-pole) come next.
    3. Bulk-fraction tells (>=70% belts -> belt balancer, >=70% walls
       -> defense, etc.) come last.
    4. Otherwise we fall back to the dominant family with low confidence.

Confidence levels: ``"high"``, ``"medium"``, ``"low"``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# Family detection helpers
# ---------------------------------------------------------------------------


def _is_furnace(name: str) -> bool:
    return name.endswith("-furnace") or name == "stone-furnace"


def _is_assembler(name: str) -> bool:
    return name.startswith("assembling-machine") or name == "assembler"


def _is_belt(name: str) -> bool:
    return (
        "transport-belt" in name
        or "underground-belt" in name
        or "splitter" in name
        or "loader" in name
    )


def _is_inserter(name: str) -> bool:
    return "inserter" in name


def _is_chest(name: str) -> bool:
    return "chest" in name or name in {
        "wooden-chest", "iron-chest", "steel-chest",
        "active-provider-chest", "passive-provider-chest",
        "storage-chest", "buffer-chest", "requester-chest",
        "logistic-chest-active-provider", "logistic-chest-passive-provider",
        "logistic-chest-storage", "logistic-chest-buffer",
        "logistic-chest-requester",
    }


def _is_pole(name: str) -> bool:
    return "electric-pole" in name or name == "substation"


def _is_wall(name: str) -> bool:
    return name in {"stone-wall", "gate"} or "wall" in name


def _is_turret(name: str) -> bool:
    return "turret" in name or "artillery" in name


def _is_solar(name: str) -> bool:
    return name == "solar-panel" or "solar-panel" in name


def _is_accumulator(name: str) -> bool:
    return "accumulator" in name


def _is_pipe(name: str) -> bool:
    return name in {"pipe", "pipe-to-ground"} or "pipe" in name


def _is_train_kit(name: str) -> bool:
    return name in {
        "rail", "straight-rail", "curved-rail", "curved-rail-a", "curved-rail-b",
        "half-diagonal-rail", "rail-ramp", "rail-support", "elevated-rail",
        "elevated-straight-rail", "elevated-curved-rail-a",
        "elevated-curved-rail-b", "elevated-half-diagonal-rail",
        "rail-signal", "rail-chain-signal", "train-stop",
    }


def _is_combinator(name: str) -> bool:
    return (
        "combinator" in name
        or name in {"constant-combinator", "decider-combinator",
                    "arithmetic-combinator", "selector-combinator"}
    )


def _is_lamp(name: str) -> bool:
    return name == "small-lamp" or name.endswith("-lamp")


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


@dataclass
class Classification:
    label: str            # short human-readable purpose (no trailing period)
    confidence: str       # 'high' | 'medium' | 'low'
    reasons: list[str]    # bullet-style notes the inventory tool can echo


def _walk_entities(obj: Any) -> Iterable[dict[str, Any]]:
    """Yield every entity in a (possibly book-shaped) blueprint."""
    if isinstance(obj, dict):
        if "entities" in obj and isinstance(obj["entities"], list):
            for e in obj["entities"]:
                if isinstance(e, dict):
                    yield e
        for v in obj.values():
            yield from _walk_entities(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk_entities(it)


def _name_counts(decoded: dict[str, Any]) -> Counter[str]:
    return Counter(e.get("name", "") for e in _walk_entities(decoded))


def _dominant_recipe(decoded: dict[str, Any]) -> Optional[str]:
    """Most-common explicit `recipe=` on an assembler-like entity, if any."""
    recipes: Counter[str] = Counter()
    for e in _walk_entities(decoded):
        rec = e.get("recipe")
        if rec:
            recipes[rec] += 1
    if not recipes:
        return None
    return recipes.most_common(1)[0][0]


def _has_planet_machine(counts: Counter[str]) -> Optional[str]:
    """Return a planet name if a planet-specific machine is present."""
    for name in counts:
        if name == "foundry":
            return "Vulcanus"
        if name == "electromagnetic-plant":
            return "Fulgora"
        if name == "biochamber":
            return "Gleba"
        if name == "agricultural-tower":
            return "Gleba"
        if name == "captive-biter-spawner":
            return "Gleba"
        if name == "cryogenic-plant":
            return "Aquilo"
        if name == "fusion-reactor" or name == "fusion-generator":
            return "Aquilo"
    return None


def classify(decoded: dict[str, Any]) -> Classification:
    """Return a one-line purpose guess for a decoded blueprint object.

    The dict can be a plain blueprint or a blueprint book. The classifier
    inspects entity names + dominant recipe across the whole tree.
    """
    if not isinstance(decoded, dict):
        return Classification("unknown structure", "low",
                              ["input is not a decoded blueprint dict"])

    counts = _name_counts(decoded)
    if not counts:
        # Possibly a deconstruction / upgrade planner with no entities.
        for k in ("deconstruction_planner", "upgrade_planner"):
            if k in decoded:
                kind = "deconstruction planner" if k.startswith("decon") else "upgrade planner"
                return Classification(kind, "high", [f"top-level key={k!r}"])
        if "blueprint_book" in decoded:
            return Classification("empty blueprint book", "high",
                                  ["blueprint_book has no entities"])
        return Classification("empty blueprint", "high",
                              ["no entities in blueprint"])

    total = sum(counts.values())
    reasons: list[str] = []
    planet = _has_planet_machine(counts)

    # ---- 1) High-confidence single-entity tells ---------------------------

    if "rocket-silo" in counts:
        return Classification(
            "rocket silo / launch pad",
            "high",
            [f"contains {counts['rocket-silo']} rocket-silo entities"],
        )
    if "nuclear-reactor" in counts and (
        "heat-pipe" in counts or "heat-exchanger" in counts
    ):
        n = counts.get("nuclear-reactor", 0)
        return Classification(
            f"nuclear plant ({n} reactor{'s' if n != 1 else ''})",
            "high",
            [f"{n} nuclear-reactor + heat infrastructure"],
        )

    # Planet-tied machines: pick whichever family dominates by count.
    planet_machines = {
        "cryogenic-plant": ("Aquilo cryo-processing block", "Aquilo"),
        "agricultural-tower": ("Gleba agriculture (agricultural-tower)", "Gleba"),
        "biochamber": ("Gleba bio-processing (biochamber)", "Gleba"),
        "electromagnetic-plant": ("Fulgora EM-plant block", "Fulgora"),
        "foundry": ("Vulcanus foundry block", "Vulcanus"),
    }
    planet_present = [
        (name, counts[name]) for name in planet_machines if counts.get(name)
    ]
    if planet_present:
        # Sort by count descending; ties broken by name for stability.
        planet_present.sort(key=lambda t: (-t[1], t[0]))
        winner, n_winner = planet_present[0]
        label, _ = planet_machines[winner]
        recipe = _dominant_recipe(decoded)
        rec_part = ""
        if winner == "foundry" and recipe:
            rec_part = f", recipe={recipe}"
        co_present = [n for n, c in planet_present if n != winner]
        co_note = ""
        if co_present:
            co_note = f"; also has {', '.join(co_present)}"
        return Classification(
            f"{label}{rec_part}",
            "high",
            [f"{n_winner} {winner}{co_note}"],
        )

    if counts.get("recycler"):
        return Classification(
            "recycler / quality recycling loop",
            "high",
            [f"{counts['recycler']} recycler"],
        )

    # ---- 2) Combined tells -----------------------------------------------

    n_solar = sum(v for n, v in counts.items() if _is_solar(n))
    n_acc = sum(v for n, v in counts.items() if _is_accumulator(n))
    if n_solar >= 4 and n_acc >= 1:
        # 60kW / panel (vanilla nominal); just report panel count.
        kw = n_solar * 60
        return Classification(
            f"solar farm ({n_solar} panels, ~{kw} kW peak)",
            "high",
            [f"{n_solar} solar panels + {n_acc} accumulators"],
        )

    n_refinery = counts.get("oil-refinery", 0)
    n_chem = counts.get("chemical-plant", 0)
    if n_refinery >= 1 and n_chem >= 1:
        return Classification(
            f"oil processing ({n_refinery} refineries, {n_chem} chem-plants)",
            "high",
            [f"oil-refinery + chemical-plant present"],
        )

    n_drill = sum(v for n, v in counts.items() if "mining-drill" in n)
    n_pole = sum(v for n, v in counts.items() if _is_pole(n))
    if n_drill >= 4 and n_pole >= 1:
        return Classification(
            f"mining outpost ({n_drill} drills)",
            "high",
            [f"{n_drill} mining drills + {n_pole} poles"],
        )

    n_furnace = sum(v for n, v in counts.items() if _is_furnace(n))
    if n_furnace >= 4:
        recipe = _dominant_recipe(decoded)
        rec_part = f", recipe={recipe}" if recipe else " (smelting recipe set in-game)"
        return Classification(
            f"smelter array ({n_furnace} furnaces{rec_part})",
            "high",
            [f"{n_furnace} furnaces dominate"],
        )

    n_assembler = sum(v for n, v in counts.items() if _is_assembler(n))
    if n_assembler >= 1:
        recipe = _dominant_recipe(decoded)
        rec_part = f" (recipe={recipe})" if recipe else ""
        confidence = "high" if recipe else "medium"
        return Classification(
            f"assembler block, {n_assembler} machines{rec_part}",
            confidence,
            [f"{n_assembler} assembling-machines"],
        )

    n_train = sum(v for n, v in counts.items() if _is_train_kit(n))
    n_stop = counts.get("train-stop", 0)
    if n_stop >= 1 and n_train >= 4:
        return Classification(
            f"train station / rail intersection ({n_stop} stop{'s' if n_stop != 1 else ''})",
            "high",
            [f"{n_stop} train-stops + {n_train} rail tiles"],
        )
    if n_train >= 8 and n_stop == 0:
        return Classification(
            "rail intersection / rail line",
            "medium",
            [f"{n_train} rail-related entities, no train-stop"],
        )

    # ---- 3) Bulk-fraction tells -----------------------------------------

    n_belt = sum(v for n, v in counts.items() if _is_belt(n))
    n_inserter = sum(v for n, v in counts.items() if _is_inserter(n))
    n_chest = sum(v for n, v in counts.items() if _is_chest(n))
    n_wall = sum(v for n, v in counts.items() if _is_wall(n))
    n_turret = sum(v for n, v in counts.items() if _is_turret(n))
    n_pipe = sum(v for n, v in counts.items() if _is_pipe(n))
    n_combinator = sum(v for n, v in counts.items() if _is_combinator(n))

    if (n_wall + n_turret) / total >= 0.6 and (n_wall + n_turret) >= 4:
        return Classification(
            f"defense wall ({n_wall} wall tiles, {n_turret} turrets)",
            "high",
            [f"walls+turrets dominate (>=60%)"],
        )

    if n_belt / total >= 0.7 and n_belt >= 8:
        # Could be a balancer, sushi belt, or just a long lane.
        n_splitter = sum(
            v for n, v in counts.items()
            if "splitter" in n
        )
        kind = ("belt balancer" if n_splitter >= 2
                else "belt run / sushi belt")
        return Classification(
            f"{kind} ({n_belt} belt tiles)",
            "medium",
            [f"belts >= 70% of entities", f"{n_splitter} splitters"],
        )

    if n_inserter >= 4 and n_chest >= 2 and n_belt <= 2:
        return Classification(
            f"logistics buffer ({n_chest} chests, {n_inserter} inserters)",
            "medium",
            [f"inserters around chests, no belt run"],
        )

    if n_combinator >= 4:
        n_lamps = sum(v for n, v in counts.items() if _is_lamp(n))
        return Classification(
            f"circuit / control logic ({n_combinator} combinators)",
            "medium",
            [f"{n_combinator} combinators, {n_lamps} lamps"],
        )

    if n_pipe / total >= 0.5 and n_pipe >= 4:
        return Classification(
            f"fluid plumbing ({n_pipe} pipe tiles)",
            "medium",
            [f"pipes dominate (>=50%)"],
        )

    # ---- 4) Single-entity / tiny blueprint -------------------------------

    if total == 1:
        only = next(iter(counts.keys()))
        if _is_pole(only):
            return Classification(
                f"single power pole ({only})",
                "high",
                ["1 entity, electric-pole family"],
            )
        return Classification(
            f"single entity ({only})",
            "high",
            ["1-entity blueprint"],
        )

    # ---- 5) Fallback: dominant family ------------------------------------

    # Pick the most common name; if that itself is a known family, use it.
    most_common, mc_count = counts.most_common(1)[0]
    pct = mc_count / total
    family = "miscellaneous"
    if planet:
        family = f"{planet}-themed build"

    return Classification(
        f"{family} (dominant: {most_common} x{mc_count})",
        "low",
        [f"could not match a strong pattern", f"top entity: {most_common} ({pct:.0%})"],
    )


# ---------------------------------------------------------------------------
# CLI (debugging aid)
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import pathlib
    import sys as _sys

    p = argparse.ArgumentParser(
        prog="blueprint_classifier",
        description="Classify a decoded blueprint into a one-line purpose label.",
    )
    p.add_argument("input", help="path to a blueprint .bp file OR a raw blueprint string")
    args = p.parse_args(argv)

    here = pathlib.Path(__file__).resolve().parent
    _sys.path.insert(0, str(here))
    import blueprint_codec  # noqa: WPS433

    arg = args.input
    src = pathlib.Path(arg)
    if src.is_file():
        raw = src.read_text(encoding="utf-8").strip()
    else:
        raw = arg.strip()
    decoded = blueprint_codec.decode(raw)
    cls = classify(decoded)
    out = {
        "label": cls.label,
        "confidence": cls.confidence,
        "reasons": cls.reasons,
    }
    json.dump(out, _sys.stdout, indent=2, ensure_ascii=False)
    _sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
