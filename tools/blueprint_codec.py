#!/usr/bin/env python3
"""Factorio 2.0 blueprint string codec (stdlib only).

A blueprint string is:

    <version_byte> + base64( zlib_deflate( utf8( json ) ) )

The version byte is currently always the ASCII character '0'.
The base64 alphabet is the standard one (A-Z a-z 0-9 + / =), NOT URL-safe.

CLI:
    python3 blueprint_codec.py decode '<string>'           # prints pretty JSON
    python3 blueprint_codec.py decode --compact '<string>' # prints compact JSON
    python3 blueprint_codec.py encode <file.json>          # prints blueprint string
    python3 blueprint_codec.py encode -                    # JSON from stdin

Library:
    from blueprint_codec import decode, encode, pack_version, unpack_version
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import zlib
from typing import Any

VERSION_BYTE = "0"


class BlueprintFormatError(ValueError):
    """Raised when a blueprint string cannot be decoded."""


def decode(blueprint_string: str) -> dict[str, Any]:
    """Decode a blueprint string into its JSON object."""
    if not isinstance(blueprint_string, str):
        raise TypeError("blueprint string must be str")
    s = blueprint_string.strip()
    if not s:
        raise BlueprintFormatError("empty blueprint string")
    if s[0] != VERSION_BYTE:
        raise BlueprintFormatError(
            f"unsupported blueprint version byte {s[0]!r}; expected {VERSION_BYTE!r}"
        )
    payload = s[1:]
    try:
        compressed = base64.b64decode(payload, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise BlueprintFormatError(f"base64 decode failed: {exc}") from exc
    try:
        raw = zlib.decompress(compressed)
    except zlib.error as exc:
        raise BlueprintFormatError(f"zlib decompress failed: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlueprintFormatError(f"json parse failed: {exc}") from exc


def encode(obj: dict[str, Any], *, level: int = 9) -> str:
    """Encode a blueprint JSON object into a blueprint string.

    `level` is the zlib compression level (0-9). Default 9 matches in-game output size.
    """
    if not isinstance(obj, dict):
        raise TypeError("blueprint object must be dict")
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    compressed = zlib.compress(raw, level)
    return VERSION_BYTE + base64.b64encode(compressed).decode("ascii")


def pack_version(major: int, minor: int, patch: int, developer: int = 0) -> int:
    """Pack a Factorio version into the uint64 used as `version` in blueprints."""
    for n in (major, minor, patch, developer):
        if not (0 <= n <= 0xFFFF):
            raise ValueError(f"version component out of range [0, 65535]: {n}")
    return (major << 48) | (minor << 32) | (patch << 16) | developer


def unpack_version(packed: int) -> tuple[int, int, int, int]:
    """Inverse of `pack_version`."""
    return (
        (packed >> 48) & 0xFFFF,
        (packed >> 32) & 0xFFFF,
        (packed >> 16) & 0xFFFF,
        packed & 0xFFFF,
    )


def _cmd_decode(args: argparse.Namespace) -> int:
    obj = decode(args.string)
    if args.compact:
        sys.stdout.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    else:
        sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0


def _cmd_encode(args: argparse.Namespace) -> int:
    if args.path == "-":
        data = sys.stdin.read()
    else:
        with open(args.path, "r", encoding="utf-8") as fh:
            data = fh.read()
    obj = json.loads(data)
    sys.stdout.write(encode(obj, level=args.level))
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blueprint_codec", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("decode", help="decode a blueprint string to JSON")
    d.add_argument("string", help="the blueprint string")
    d.add_argument("--compact", action="store_true", help="emit compact JSON (no indent)")
    d.set_defaults(func=_cmd_decode)

    e = sub.add_parser("encode", help="encode a JSON file to a blueprint string")
    e.add_argument("path", help="path to a JSON file, or '-' for stdin")
    e.add_argument("--level", type=int, default=9, help="zlib level 0-9 (default 9)")
    e.set_defaults(func=_cmd_encode)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


# ---------------------------------------------------------------------------
# Self-test: round-trip a known small blueprint (single small electric pole).
# Run with `python3 blueprint_codec.py` (no args) to execute it.
# ---------------------------------------------------------------------------

_KNOWN_STRING = (
    "0eNp9js0KwjAQhN9lzilU7Q/Nq4hIWxdZSDYlScVS8u4m9eDNy8AOM9/OjsmstHiWCL2DZycB+roj8FNGUzwZL"
    "UEj2NGYigzN0fNcLc4QkgLLg97Qp3RTIIkcmb6A49justqJfA6ofyCFxYXcdVI+Zl6tsGVNBcuRbO79hiq8yIc"
    "j3HbnoRmGtqn7rusvKX0AwFVGCg=="
)

_KNOWN_OBJECT = {
    "blueprint": {
        "icons": [{"signal": {"name": "small-electric-pole"}, "index": 1}],
        "entities": [
            {"entity_number": 1, "name": "small-electric-pole", "position": {"x": 0, "y": 0}}
        ],
        "item": "blueprint",
        "version": 562949954076673,
    }
}


def _selftest() -> int:
    obj = decode(_KNOWN_STRING)
    assert obj == _KNOWN_OBJECT, f"decode mismatch: {obj!r}"
    re_encoded = encode(_KNOWN_OBJECT)
    obj2 = decode(re_encoded)
    assert obj2 == _KNOWN_OBJECT, "re-encoded blueprint did not round-trip"
    assert pack_version(2, 0, 76) == 562949958402048
    assert unpack_version(562949954076673) == (2, 0, 10, 1)
    print("blueprint_codec self-test OK")
    print("  decoded keys:", list(obj["blueprint"].keys()))
    print("  re-encoded len:", len(re_encoded))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(_selftest())
    sys.exit(main())
