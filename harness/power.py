"""Electric-pole placement helpers.

In the MVP, pole placement is performed inline by `layout.py` (the
solar field places medium-electric-poles; the smelter array uses
burner-only entities and so doesn't need power coverage). This module
is a stub for a future v2 that needs to retrofit power onto an existing
layout.
"""

from __future__ import annotations

from harness.layout import LayoutResult


def cover_with_poles(layout: LayoutResult, *, pole: str = "small-electric-pole") -> None:  # pragma: no cover - stub
    """Reserved for v2 builders. Currently a no-op."""
    return
