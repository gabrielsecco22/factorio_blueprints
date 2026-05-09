"""Belt + inserter wiring helpers.

In the MVP, wiring is performed inline by `layout.py` (the smelter
array places its own belts and inserters; the solar field has no
material flow). This module is a stub that defines the public interface
so a future, more complex builder can plug in here without rewiring
the orchestrator.
"""

from __future__ import annotations

from harness.layout import LayoutResult


def add_input_output_belts(layout: LayoutResult, *, side: str = "north") -> None:  # pragma: no cover - stub
    """Reserved for v2 builders. Currently a no-op."""
    return
