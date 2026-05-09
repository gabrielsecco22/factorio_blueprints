"""Wraps `tools/blueprint_codec.py` so the harness can encode/decode
without forcing callers to fiddle with sys.path.
"""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CODEC_PATH = REPO_ROOT / "tools" / "blueprint_codec.py"

_spec = importlib.util.spec_from_file_location("blueprint_codec", _CODEC_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"could not load blueprint codec from {_CODEC_PATH}")
_codec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_codec)


# Packed Factorio version 2.0.76. Verified by `tools/blueprint_codec.py`'s
# self-test (`pack_version(2,0,76) == 562949958402048`).
PACKED_VERSION_2_0_76 = 562949958402048


def encode(obj: dict[str, Any], *, level: int = 9) -> str:
    """Encode a blueprint JSON object into a paste-ready blueprint string."""
    return _codec.encode(obj, level=level)


def decode(blueprint_string: str) -> dict[str, Any]:
    """Decode a blueprint string into its JSON object."""
    return _codec.decode(blueprint_string)


def pack_version(major: int, minor: int, patch: int, developer: int = 0) -> int:
    """Pack a Factorio version into the uint64 used in `blueprint.version`."""
    return _codec.pack_version(major, minor, patch, developer)
