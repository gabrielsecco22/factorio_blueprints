#!/usr/bin/env python3
"""Manage a local mirror of the user's Factorio blueprint library.

This tool gives you read/write access to a *file-system* library at
``library/personal/`` -- one ``.bp`` file per blueprint string, books
laid out as directories with a ``_book.json`` manifest.

It does not require Factorio to be running. The optional ``from-game``
subcommand makes a best-effort pass over
``~/.factorio/blueprint-storage-2.dat`` to enumerate what's stored
there; see ``docs/blueprint_storage_format.md`` for what currently
parses and what doesn't. ``to-game`` is intentionally not implemented
because clobbering ``blueprint-storage-2.dat`` will lose blueprints.

CLI summary::

    blueprint_storage.py list
    blueprint_storage.py show   <name>
    blueprint_storage.py search <text>
    blueprint_storage.py import-string <bp-string> [name]
    blueprint_storage.py import-file   <path>      [name]
    blueprint_storage.py export <name> [-o file]
    blueprint_storage.py from-game [--dry-run] [--source PATH]
    blueprint_storage.py to-game   --i-have-a-backup [--dry-run]

Internal API::

    from tools.blueprint_storage import LibraryStore
    store = LibraryStore("library/personal")
    for entry in store.list():
        print(entry.name, entry.label)
    store.add(string, name="solar-array-3MW")
    decoded = store.get("solar-array-3MW")
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Allow running as a script (``python3 tools/blueprint_storage.py ...``) by
# putting ``tools/`` on the path before importing siblings.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import blueprint_codec  # noqa: E402
import blueprint_storage_format as bsf  # noqa: E402


DEFAULT_LIBRARY = Path(__file__).resolve().parent.parent / "library" / "personal"
DEFAULT_GAME_FILE = Path.home() / ".factorio" / "blueprint-storage-2.dat"

_NAME_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slugify(name: str, fallback: str = "blueprint") -> str:
    s = _NAME_SLUG_RE.sub("-", name).strip("-")
    return s or fallback


def _decoded_kind(decoded: dict) -> str:
    """Return the top-level key of a blueprint string ('blueprint', 'blueprint_book',
    'deconstruction_planner', 'upgrade_planner') -- or 'unknown'."""
    for key in ("blueprint", "blueprint_book", "deconstruction_planner",
                "upgrade_planner"):
        if key in decoded:
            return key
    return "unknown"


def _decoded_label(decoded: dict) -> str:
    body = decoded.get(_decoded_kind(decoded), {})
    return body.get("label") or ""


def _decoded_description(decoded: dict) -> str:
    body = decoded.get(_decoded_kind(decoded), {})
    return body.get("description") or ""


def _decoded_size(decoded: dict) -> dict:
    """Quick metrics for the list view (counts entities/tiles, etc)."""
    body = decoded.get(_decoded_kind(decoded), {})
    out: dict[str, int] = {}
    for k in ("entities", "tiles", "schedules", "icons"):
        if k in body and isinstance(body[k], list):
            out[k] = len(body[k])
    if "blueprints" in body and isinstance(body["blueprints"], list):
        out["blueprints"] = len(body["blueprints"])
    return out


# ---------------------------------------------------------------------------
# LibraryStore: filesystem-backed mirror
# ---------------------------------------------------------------------------


@dataclass
class LibraryEntry:
    """One file-system entry: either a single .bp file or a book directory."""

    path: Path
    name: str
    kind: str                    # 'blueprint' | 'blueprint_book' | ...
    label: str = ""
    description: str = ""
    decoded: dict | None = None
    sizes: dict[str, int] = field(default_factory=dict)


class LibraryStore:
    """File-system-backed library at ``root/`` (default ``library/personal``)."""

    def __init__(self, root: Path | str = DEFAULT_LIBRARY):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- enumeration ---------------------------------------------------------

    def list(self) -> Iterator[LibraryEntry]:
        for child in sorted(self.root.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_file() and child.suffix == ".bp":
                yield self._entry_from_bp(child)
            elif child.is_dir():
                book_meta = child / "_book.json"
                if book_meta.exists():
                    try:
                        meta = json.loads(book_meta.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        meta = {}
                    yield LibraryEntry(
                        path=child, name=child.name, kind="blueprint_book",
                        label=meta.get("label", ""),
                        description=meta.get("description", ""),
                        sizes={"blueprints": sum(1 for _ in child.glob("*.bp"))},
                    )

    def _entry_from_bp(self, path: Path) -> LibraryEntry:
        try:
            string = path.read_text(encoding="utf-8").strip()
            decoded = blueprint_codec.decode(string)
            kind = _decoded_kind(decoded)
            return LibraryEntry(
                path=path, name=path.stem, kind=kind,
                label=_decoded_label(decoded),
                description=_decoded_description(decoded),
                decoded=decoded, sizes=_decoded_size(decoded),
            )
        except Exception as exc:                                    # noqa: BLE001
            return LibraryEntry(
                path=path, name=path.stem, kind="unparseable",
                description=f"decode error: {exc}",
            )

    # -- get -----------------------------------------------------------------

    def get(self, name: str) -> dict:
        path = self._resolve(name)
        if path is None:
            raise FileNotFoundError(name)
        return blueprint_codec.decode(path.read_text(encoding="utf-8").strip())

    def get_string(self, name: str) -> str:
        path = self._resolve(name)
        if path is None:
            raise FileNotFoundError(name)
        return path.read_text(encoding="utf-8").strip()

    def _resolve(self, name: str) -> Path | None:
        # Direct match: library/personal/<name>.bp
        p = self.root / f"{name}.bp"
        if p.exists():
            return p
        # Book child: library/personal/<book>/<name>.bp
        for book in self.root.iterdir():
            if book.is_dir():
                p = book / f"{name}.bp"
                if p.exists():
                    return p
        # Or full path that matches
        p = Path(name)
        if p.is_file():
            return p
        return None

    # -- write ---------------------------------------------------------------

    def add(self, blueprint_string: str, *, name: str | None = None,
            book: str | None = None, overwrite: bool = False) -> Path:
        # Validate: must round-trip through the codec.
        decoded = blueprint_codec.decode(blueprint_string)
        kind = _decoded_kind(decoded)

        if name is None:
            label = _decoded_label(decoded)
            name = _slugify(label) if label else f"{kind}-{int(time.time())}"
        else:
            name = _slugify(name)

        target_dir = self.root if book is None else self.root / _slugify(book)
        target_dir.mkdir(parents=True, exist_ok=True)
        if book is not None:
            self._write_book_meta(target_dir, label=book, description="")

        target = target_dir / f"{name}.bp"
        if target.exists() and not overwrite:
            stem, suffix = target.stem, target.suffix
            i = 2
            while (target_dir / f"{stem}-{i}{suffix}").exists():
                i += 1
            target = target_dir / f"{stem}-{i}{suffix}"

        target.write_text(blueprint_string.strip() + "\n", encoding="utf-8")
        return target

    def _write_book_meta(self, dir_path: Path, *, label: str,
                         description: str, icons: list | None = None) -> Path:
        meta_path = dir_path / "_book.json"
        meta = {"label": label, "description": description, "icons": icons or []}
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        return meta_path

    # -- search --------------------------------------------------------------

    def search(self, query: str) -> list[LibraryEntry]:
        q = query.lower()
        out: list[LibraryEntry] = []
        for entry in self.list():
            haystack = f"{entry.name}\n{entry.label}\n{entry.description}".lower()
            if q in haystack:
                out.append(entry)
        return out


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> int:
    store = LibraryStore(args.library)
    rows = list(store.list())
    if not rows:
        print(f"(empty library at {store.root})")
        return 0
    print(f"{store.root}: {len(rows)} entries")
    for entry in rows:
        sizes = " ".join(f"{k}={v}" for k, v in entry.sizes.items())
        sizes = f" [{sizes}]" if sizes else ""
        label = entry.label or "(no label)"
        print(f"  {entry.name}  {entry.kind}  {label!r}{sizes}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    store = LibraryStore(args.library)
    try:
        decoded = store.get(args.name)
    except FileNotFoundError:
        print(f"not found: {args.name}", file=sys.stderr)
        return 1
    json.dump(decoded, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    store = LibraryStore(args.library)
    matches = store.search(args.text)
    if not matches:
        print(f"no matches for {args.text!r}")
        return 1
    for entry in matches:
        print(f"  {entry.name}  {entry.kind}  {entry.label!r}")
    return 0


def _cmd_import_string(args: argparse.Namespace) -> int:
    store = LibraryStore(args.library)
    target = store.add(args.string, name=args.name, book=args.book,
                       overwrite=args.overwrite)
    print(f"wrote {target}")
    return 0


def _cmd_import_file(args: argparse.Namespace) -> int:
    store = LibraryStore(args.library)
    raw = Path(args.path).read_text(encoding="utf-8").strip()
    name = args.name or Path(args.path).stem
    target = store.add(raw, name=name, book=args.book, overwrite=args.overwrite)
    print(f"wrote {target}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    store = LibraryStore(args.library)
    try:
        s = store.get_string(args.name)
    except FileNotFoundError:
        print(f"not found: {args.name}", file=sys.stderr)
        return 1
    if args.output:
        Path(args.output).write_text(s + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(s + "\n")
    return 0


def _cmd_from_game(args: argparse.Namespace) -> int:
    src = Path(args.source)
    if not src.exists():
        print(f"binary library not found: {src}", file=sys.stderr)
        return 1

    header, entries = bsf.parse_storage_file(str(src))
    used = sum(1 for e in entries if e.used)
    drifted = sum(1 for e in entries if e.parse_error and e.used)

    print(f"source: {src} ({src.stat().st_size:,} bytes)")
    print(f"factorio version: {'.'.join(str(x) for x in header.version)}")
    print(f"migrations: {len(header.migrations)}")
    print(f"prototype categories: {len(header.prototype_index.by_category)}")
    print(f"object_count (header): {header.object_count}")
    print(f"entries walked: {len(entries)} (used={used}, "
          f"unused={len(entries)-used}, drifted={drifted})")

    print()
    print(f"{'idx':>4} {'kind':<22} {'label':<32} {'csize':>10}  {'offset':>10}")
    for e in entries:
        if not e.used:
            print(f"{e.index:>4} (slot)              "
                  f"{'(unused)':<32} {'-':>10}  {e.offset:>#10x}")
            continue
        label = (e.label or "")[:32].replace("\n", " ")
        csize = f"{e.content_size:,}" if e.content_size is not None else "-"
        print(f"{e.index:>4} {e.kind or '?':<22} {label!r:<32} {csize:>10}  "
              f"{e.offset:>#10x}")
        if e.parse_error:
            print(f"     ! {e.parse_error}")

    print()
    if args.dry_run:
        print("DRY RUN: nothing extracted. Re-run without --dry-run to save "
              "what we can to the library.")
        return 0

    store = LibraryStore(args.library)
    saved = 0
    for e in entries:
        if not e.used or e.parse_error or e.kind != "blueprint":
            continue
        # We only re-encode blueprints whose body we captured. Right now
        # the body is opaque binary -- we can't turn it into a blueprint
        # *string* without a full content parser. So we save metadata as
        # JSON for diagnostic purposes, but skip writing a .bp file.
        meta = {
            "kind": e.kind,
            "item_name": e.item_name,
            "label": e.label,
            "description": e.description,
            "generation": e.generation,
            "offset": hex(e.offset),
            "content_size": e.content_size,
            "_note": "Body captured as binary blob; re-encoding to a "
                     "blueprint string is not yet implemented. Use the "
                     "in-game Export string workflow then run "
                     "`blueprint_storage.py import-string`.",
        }
        slug = _slugify(e.label or f"binary-{e.index}",
                        fallback=f"binary-{e.index}")
        out = store.root / "_from_game" / f"{slug}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        saved += 1
    print(f"saved {saved} metadata stubs under {store.root / '_from_game'}/")
    print("To extract real blueprint strings, see "
          "docs/blueprint_storage_format.md (manual workflow).")
    return 0


def _cmd_to_game(args: argparse.Namespace) -> int:
    if not args.i_have_a_backup:
        print("refusing to write without --i-have-a-backup", file=sys.stderr)
        print("Run `cp ~/.factorio/blueprint-storage-2.dat "
              "~/.factorio/blueprint-storage-2.dat.bak.$(date -u +%Y%m%dT%H%M%SZ)` "
              "first.", file=sys.stderr)
        return 2

    if args.dry_run:
        print("DRY RUN: would back up and rewrite "
              f"{args.target} -- but the binary writer is not implemented.")
        print("This subcommand is a stub. Re-importing blueprints into the "
              "game requires the in-game 'Import string' UI for now.")
        return 0

    print("to-game write-back is not implemented (see "
          "docs/blueprint_storage_format.md).", file=sys.stderr)
    return 3


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="blueprint_storage",
        description="Manage a local mirror of the Factorio blueprint library.",
    )
    p.add_argument("--library", default=str(DEFAULT_LIBRARY),
                   help=f"library root (default: {DEFAULT_LIBRARY})")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list", help="list local blueprints")
    sp.set_defaults(func=_cmd_list)

    sp = sub.add_parser("show", help="decode and pretty-print a blueprint")
    sp.add_argument("name")
    sp.set_defaults(func=_cmd_show)

    sp = sub.add_parser("search", help="full-text search labels and descriptions")
    sp.add_argument("text")
    sp.set_defaults(func=_cmd_search)

    sp = sub.add_parser("import-string", help="save a blueprint string to the library")
    sp.add_argument("string")
    sp.add_argument("name", nargs="?")
    sp.add_argument("--book", help="put the blueprint in this book directory")
    sp.add_argument("--overwrite", action="store_true",
                    help="overwrite an existing file with the same slug")
    sp.set_defaults(func=_cmd_import_string)

    sp = sub.add_parser("import-file", help="save a blueprint string from a file")
    sp.add_argument("path")
    sp.add_argument("name", nargs="?")
    sp.add_argument("--book")
    sp.add_argument("--overwrite", action="store_true")
    sp.set_defaults(func=_cmd_import_file)

    sp = sub.add_parser("export", help="print or save a stored blueprint string")
    sp.add_argument("name")
    sp.add_argument("-o", "--output")
    sp.set_defaults(func=_cmd_export)

    sp = sub.add_parser("from-game",
                        help="best-effort import from blueprint-storage-2.dat")
    sp.add_argument("--source", default=str(DEFAULT_GAME_FILE),
                    help=f"path to blueprint-storage-2.dat (default: {DEFAULT_GAME_FILE})")
    sp.add_argument("--dry-run", action="store_true",
                    help="report what was found without writing files")
    sp.set_defaults(func=_cmd_from_game)

    sp = sub.add_parser("to-game",
                        help="(STUB) write back to blueprint-storage-2.dat -- DANGEROUS")
    sp.add_argument("--target", default=str(DEFAULT_GAME_FILE))
    sp.add_argument("--i-have-a-backup", action="store_true",
                    help="confirm you have a timestamped backup of the target file")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=_cmd_to_game)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
