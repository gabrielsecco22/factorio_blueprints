"""Factorio blueprint synthesis harness.

A deterministic Python pipeline that turns a `BuildSpec` into a
paste-ready Factorio 2.0.76 blueprint string. Each module in this
package corresponds to one synthesis stage so that, in a future LLM
driven version, it can be swapped for a sub-agent prompt without
re-architecting the pipeline.

Modules:
    spec        - dataclasses describing what to build.
    catalog     - lazy loaders for `specs/*.json`.
    plan        - Planner: spec -> ProductionPlan (recipe, machine, count).
    layout      - Layout: ProductionPlan -> EntityGrid (positions, dirs).
    wiring      - Belts and inserters between machines and sources/sinks.
    power       - Electric-pole coverage for any electric entities.
    encode      - Wraps tools/blueprint_codec.py.
    validate    - Collision, belt continuity, inserter reach, schema.
    orchestrator - End-to-end pipeline driver.

Public API:
    from harness import synthesize, BuildSpec, SynthesisResult
"""

from harness.orchestrator import synthesize, SynthesisResult  # noqa: F401
from harness.spec import BuildSpec  # noqa: F401

__all__ = ["synthesize", "SynthesisResult", "BuildSpec"]
