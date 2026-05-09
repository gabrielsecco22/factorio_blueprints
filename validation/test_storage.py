#!/usr/bin/env python3
"""Tests for tools/blueprint_storage.py and blueprint_storage_format.py.

Stdlib-only. Run with::

    python3 validation/test_storage.py

Exits non-zero on the first failure. The script never writes to
``~/.factorio/blueprint-storage-2.dat`` -- it only reads from it.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

# Make the tools/ directory importable.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))

import blueprint_codec  # noqa: E402
import blueprint_storage  # noqa: E402
import blueprint_storage_format as bsf  # noqa: E402


# A small known-good blueprint string (single small-electric-pole, used by
# tools/blueprint_codec.py's self-test).
KNOWN_STRING = blueprint_codec._KNOWN_STRING
KNOWN_OBJECT = blueprint_codec._KNOWN_OBJECT


_failures: list[str] = []


def check(cond: bool, message: str) -> None:
    if not cond:
        _failures.append(message)
        print(f"  FAIL: {message}")
    else:
        print(f"  ok: {message}")


def test_round_trip_in_temp_library() -> None:
    print("[test_round_trip_in_temp_library]")
    with tempfile.TemporaryDirectory() as tmp:
        store = blueprint_storage.LibraryStore(Path(tmp))
        # Add the blueprint with an explicit name.
        path = store.add(KNOWN_STRING, name="electric-pole")
        check(path.exists(), f"file written at {path}")
        check(path.read_text(encoding="utf-8").strip() == KNOWN_STRING.strip(),
              "file contents match original blueprint string")

        # List it back.
        rows = list(store.list())
        check(len(rows) == 1, "library lists exactly one entry")
        check(rows[0].name == "electric-pole", "entry name matches slug")
        check(rows[0].kind == "blueprint", "entry kind is 'blueprint'")
        check(rows[0].sizes.get("entities") == 1,
              "entity count derived from decoded body")

        # get() round-trips through the codec.
        decoded = store.get("electric-pole")
        check(decoded == KNOWN_OBJECT, "decoded body equals KNOWN_OBJECT")

        # get_string() returns the exact stored string.
        s = store.get_string("electric-pole")
        check(s.strip() == KNOWN_STRING.strip(),
              "get_string returns original string verbatim")

        # search() finds it by slug.
        matches = store.search("electric")
        check(len(matches) == 1, "search('electric') finds it")


def test_book_layout() -> None:
    print("[test_book_layout]")
    with tempfile.TemporaryDirectory() as tmp:
        store = blueprint_storage.LibraryStore(Path(tmp))
        store.add(KNOWN_STRING, name="pole-a", book="solar-array")
        store.add(KNOWN_STRING, name="pole-b", book="solar-array")
        rows = list(store.list())
        # 1 book directory at top level.
        kinds = sorted(e.kind for e in rows)
        check(kinds == ["blueprint_book"],
              f"top-level lists one book, got {kinds}")
        check(rows[0].sizes.get("blueprints") == 2,
              "book contains 2 blueprints")
        meta = (Path(tmp) / "solar-array" / "_book.json")
        check(meta.exists(), "_book.json was written")


def test_invalid_blueprint_rejected() -> None:
    print("[test_invalid_blueprint_rejected]")
    with tempfile.TemporaryDirectory() as tmp:
        store = blueprint_storage.LibraryStore(Path(tmp))
        try:
            store.add("not-a-blueprint")
        except blueprint_codec.BlueprintFormatError:
            check(True, "garbage input raises BlueprintFormatError")
            return
        check(False, "garbage input should have raised")


def test_dry_run_against_real_file() -> None:
    print("[test_dry_run_against_real_file]")
    real = Path.home() / ".factorio" / "blueprint-storage-2.dat"
    if not real.exists():
        print(f"  skipped: {real} not present")
        return
    header, entries = bsf.parse_storage_file(str(real))
    check(header.version[0] == 2, f"file is Factorio 2.x (got {header.version})")
    check(header.object_count > 0,
          f"object_count > 0 (got {header.object_count})")
    check(len(entries) >= 1, "at least one entry parsed")
    used_blueprints = [e for e in entries if e.used and e.kind == "blueprint"]
    check(len(used_blueprints) >= 1,
          f"at least one used blueprint observed "
          f"(got {len(used_blueprints)})")
    # And every parsed blueprint should have a content blob we captured.
    for e in used_blueprints:
        check(e.raw_content is not None and len(e.raw_content) == e.content_size,
              f"entry {e.index} content captured "
              f"({len(e.raw_content) if e.raw_content else 0} of "
              f"{e.content_size} bytes)")


def test_cli_list_on_empty_library() -> None:
    print("[test_cli_list_on_empty_library]")
    with tempfile.TemporaryDirectory() as tmp:
        rc = blueprint_storage.main(["--library", tmp, "list"])
        check(rc == 0, "list on empty library returns 0")


def test_cli_to_game_refuses_without_flag() -> None:
    print("[test_cli_to_game_refuses_without_flag]")
    rc = blueprint_storage.main(["to-game", "--target", "/dev/null"])
    check(rc != 0, "to-game refuses without --i-have-a-backup")


def main() -> int:
    tests = [
        test_round_trip_in_temp_library,
        test_book_layout,
        test_invalid_blueprint_rejected,
        test_dry_run_against_real_file,
        test_cli_list_on_empty_library,
        test_cli_to_game_refuses_without_flag,
    ]
    for t in tests:
        try:
            t()
        except Exception:                                            # noqa: BLE001
            traceback.print_exc()
            _failures.append(f"{t.__name__} raised")

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} check(s) failed")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("OK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
