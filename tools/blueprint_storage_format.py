#!/usr/bin/env python3
"""Best-effort reader for Factorio 2.0 ``blueprint-storage-2.dat``.

The binary format is undocumented. This module implements only the parts of
the format that we have verified against the user's actual file (Factorio
2.0.76 + Space Age + Quality + Elevated Rails + 34 third-party mods).

Verified structure (see ``docs/blueprint_storage_format.md``)::

    file := header library_state objects
    header :=
        version (4 x u16 LE) -- e.g. 2.0.76.0
        u8 (=0)
        count8 migrations
        migration[count8]   -- (string mod_name, string source_file)
        prototype_index
    prototype_index :=
        count16 categories
        category[count16]   -- (string cat_name, count16 nc, name[nc])
        name := (u16 id, string name)        -- for most categories
        name := (u8 id, string name)         -- for the 'quality' category
    library_state :=
        u8 lib_state (=0)
        u8 (=0)
        u32 generation_counter
        u32 unix_timestamp
        u32 (=0)
        u8 sentinel (=1)
        u32 object_count
    object := used_object | unused_object
    unused_object := u8 (=0)
    used_object :=
        u8 is_used (=1)
        u8 prefix_byte         -- 0=blueprint, 1=blueprint-book,
                                 -- 2=deconstruction-planner,
                                 -- 3=upgrade-planner (observed)
        u32 generation
        u16 item_id            -- references the prototype index
        string label
        string description
        ... handler-specific bytes

Beyond the per-object envelope, the content body of each blueprint/book
holds the full entity layout, schedules, tiles, snap-to-grid info, etc.
That body uses a delta-compressed entity-by-entity format that we do
*not* fully decode here. For blueprints we read a content-size length
prefix and skip the body; for books we currently fail on the nested
recursion.

If parsing drifts, callers should treat the file as opaque and fall back
to the in-game "Export string" workflow.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from typing import Any, BinaryIO


class StorageFormatError(ValueError):
    """Raised when the binary file does not match expected layout."""


# ---------------------------------------------------------------------------
# Primitive stream
# ---------------------------------------------------------------------------


class _Stream:
    """Minimal little-endian binary reader. Mirrors the asheiduk decoder API."""

    __slots__ = ("buf", "pos", "_len")

    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0
        self._len = len(buf)

    def remaining(self) -> int:
        return self._len - self.pos

    def tell(self) -> int:
        return self.pos

    def seek(self, p: int) -> None:
        self.pos = p

    def _read(self, fmt: str, n: int) -> Any:
        if self.pos + n > self._len:
            raise StorageFormatError(
                f"unexpected EOF: need {n} bytes at offset {self.pos:#x}"
            )
        v = struct.unpack_from(fmt, self.buf, self.pos)[0]
        self.pos += n
        return v

    def u8(self) -> int:
        return self._read("<B", 1)

    def u16(self) -> int:
        return self._read("<H", 2)

    def u32(self) -> int:
        return self._read("<I", 4)

    def f32(self) -> float:
        return self._read("<f", 4)

    def f64(self) -> float:
        return self._read("<d", 8)

    def count(self) -> int:
        """Length-prefix used by strings: u8, with 0xff escaping to u32."""
        n = self.u8()
        if n == 0xFF:
            return self.u32()
        return n

    def string(self) -> str:
        n = self.count()
        if self.pos + n > self._len:
            raise StorageFormatError(
                f"string of length {n} at {self.pos:#x} exceeds file"
            )
        s = self.buf[self.pos : self.pos + n].decode("utf-8", errors="replace")
        self.pos += n
        return s

    def bytes(self, n: int) -> bytes:
        if self.pos + n > self._len:
            raise StorageFormatError(
                f"slice of {n} bytes at {self.pos:#x} exceeds file"
            )
        b = self.buf[self.pos : self.pos + n]
        self.pos += n
        return b

    def expect(self, *expected: int) -> int:
        v = self.u8()
        if v not in expected:
            raise StorageFormatError(
                f"expected one of {[hex(x) for x in expected]} at "
                f"{self.pos - 1:#x}, got {v:#x}"
            )
        return v


# ---------------------------------------------------------------------------
# Top-level parsed structures
# ---------------------------------------------------------------------------


@dataclass
class Migration:
    mod: str
    source_file: str


@dataclass
class PrototypeIndex:
    # (category_name, prototype_id) -> internal_name
    by_id: dict[tuple[str, int], str] = field(default_factory=dict)
    # category_name -> {prototype_id: internal_name}
    by_category: dict[str, dict[int, str]] = field(default_factory=dict)

    def add(self, category: str, pid: int, name: str) -> None:
        self.by_id[(category, pid)] = name
        self.by_category.setdefault(category, {})[pid] = name

    def find_object_kind(self, item_id: int) -> tuple[str | None, str | None]:
        """Look up a top-level item id across the four library-object categories."""
        for cat in ("blueprint", "blueprint-book",
                    "deconstruction-item", "upgrade-item"):
            n = self.by_category.get(cat, {}).get(item_id)
            if n is not None:
                return cat, n
        return None, None


@dataclass
class StorageHeader:
    version: tuple[int, int, int, int]
    migrations: list[Migration]
    prototype_index: PrototypeIndex
    generation_counter: int
    timestamp: int
    object_count: int


@dataclass
class LibraryEntry:
    """A best-effort summary of one top-level entry in blueprint-storage-2.dat."""

    index: int
    used: bool
    offset: int
    kind: str | None = None             # "blueprint", "blueprint-book", ...
    item_name: str | None = None        # internal prototype name
    item_id: int | None = None
    prefix_byte: int | None = None
    generation: int | None = None
    label: str | None = None
    description: str | None = None
    content_size: int | None = None
    content_offset: int | None = None
    parse_error: str | None = None
    # If we extracted the body raw, store it for future re-encoding work
    raw_content: bytes | None = None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


PREFIX_TO_KIND = {
    0: "blueprint",
    1: "blueprint-book",
    2: "deconstruction-planner",
    3: "upgrade-planner",
}


# Categories that use a u8 (instead of u16) for both count and id width.
# In Factorio 2.0 this is just 'quality' — vs 1.x where 'tile' was the
# special-cased one.
_NARROW_ID_CATEGORIES = frozenset({"quality"})


def _parse_header(s: _Stream) -> StorageHeader:
    version = (s.u16(), s.u16(), s.u16(), s.u16())
    s.expect(0x00)                              # post-version sentinel

    mig_count = s.u8()                          # count8 of migrations
    migrations = []
    for _ in range(mig_count):
        migrations.append(Migration(mod=s.string(), source_file=s.string()))

    pi = PrototypeIndex()
    cat_count = s.u16()
    for _ in range(cat_count):
        cat = s.string()
        narrow = cat in _NARROW_ID_CATEGORIES
        nc = s.u8() if narrow else s.u16()
        for _ in range(nc):
            pid = s.u8() if narrow else s.u16()
            pi.add(cat, pid, s.string())

    s.expect(0x00)                              # lib_state byte (always 0)
    s.expect(0x00)
    generation_counter = s.u32()
    timestamp = s.u32()
    s.u32()                                     # 4 zero bytes (reserved)
    s.expect(0x01)                              # second sentinel
    object_count = s.u32()

    return StorageHeader(
        version=version,
        migrations=migrations,
        prototype_index=pi,
        generation_counter=generation_counter,
        timestamp=timestamp,
        object_count=object_count,
    )


def _parse_object_envelope(s: _Stream, header: StorageHeader,
                           index: int) -> LibraryEntry:
    """Read one object entry envelope. Skips the body for blueprints (using the
    embedded content size). For other kinds it sets ``parse_error`` and stops.
    """
    off = s.tell()
    is_used = s.u8()
    if is_used == 0:
        return LibraryEntry(index=index, used=False, offset=off)
    if is_used != 1:
        return LibraryEntry(
            index=index, used=False, offset=off,
            parse_error=f"unexpected is_used byte {is_used:#x}",
        )

    prefix_byte = s.u8()
    generation = s.u32()
    item_id = s.u16()
    cat, name = header.prototype_index.find_object_kind(item_id)
    kind = PREFIX_TO_KIND.get(prefix_byte, cat or f"unknown-prefix-{prefix_byte}")

    try:
        label = s.string()
        description = s.string()
    except StorageFormatError as exc:
        return LibraryEntry(
            index=index, used=True, offset=off,
            kind=kind, item_id=item_id, item_name=name, prefix_byte=prefix_byte,
            generation=generation,
            parse_error=f"label/desc parse failed: {exc}",
        )

    entry = LibraryEntry(
        index=index, used=True, offset=off, kind=kind, item_id=item_id,
        item_name=name, prefix_byte=prefix_byte, generation=generation,
        label=label, description=description,
    )

    if prefix_byte == 0:                        # plain blueprint: has length-prefix
        try:
            extra = s.u8()                      # observed: always 0x00
            content_size = s.count()
            content_off = s.tell()
            if content_off + content_size > s._len:
                entry.parse_error = (
                    f"content size {content_size} at {content_off:#x} "
                    f"overflows file"
                )
                return entry
            entry.content_size = content_size
            entry.content_offset = content_off
            entry.raw_content = s.bytes(content_size)
        except StorageFormatError as exc:
            entry.parse_error = f"blueprint envelope: {exc}"
        return entry

    # For books, deconstruction planners, upgrade planners we have not
    # nailed the size header yet. Stop the walk to avoid drifting through
    # millions of bytes of garbage.
    entry.parse_error = (
        f"prefix {prefix_byte} ({kind}) body skipping not implemented; "
        f"top-level walk stops here"
    )
    return entry


def parse_storage(data: bytes, *, max_objects: int | None = None
                  ) -> tuple[StorageHeader, list[LibraryEntry]]:
    """Parse the full ``blueprint-storage-2.dat`` byte buffer.

    Returns the header plus a list of LibraryEntry. Walks until the first
    parse error. The walk is *strictly* read-only.
    """
    s = _Stream(data)
    header = _parse_header(s)
    entries: list[LibraryEntry] = []
    limit = header.object_count if max_objects is None else min(
        header.object_count, max_objects)
    for i in range(limit):
        if s.remaining() == 0:
            break
        entry = _parse_object_envelope(s, header, i)
        entries.append(entry)
        if entry.parse_error and entry.used:
            # Drift-prevention: stop the walk when we see something we
            # can't safely skip past (books and planners).
            break
    return header, entries


def parse_storage_file(path: str, *, max_objects: int | None = None
                       ) -> tuple[StorageHeader, list[LibraryEntry]]:
    with open(path, "rb") as fh:
        data = fh.read()
    return parse_storage(data, max_objects=max_objects)


# ---------------------------------------------------------------------------
# Self-test (run as `python3 blueprint_storage_format.py` to exercise the
# parser against the user's real file).
# ---------------------------------------------------------------------------


def _selftest(path: str = "/home/gabriel/.factorio/blueprint-storage-2.dat") -> int:
    import os
    if not os.path.exists(path):
        print(f"selftest: {path} not found, skipping")
        return 0
    header, entries = parse_storage_file(path)
    used = sum(1 for e in entries if e.used)
    drifted = sum(1 for e in entries if e.parse_error and e.used)
    print(f"version: {header.version}")
    print(f"migrations: {len(header.migrations)}")
    print(f"prototype categories: {len(header.prototype_index.by_category)}")
    print(f"object_count (header): {header.object_count}")
    print(f"entries walked: {len(entries)}, used: {used}, "
          f"drifted: {drifted}")
    for e in entries[:5]:
        print(f"  entry {e.index}: used={e.used} kind={e.kind} "
              f"label={e.label!r} csize={e.content_size}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest(*sys.argv[1:]))
