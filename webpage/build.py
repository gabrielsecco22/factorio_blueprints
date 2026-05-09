#!/usr/bin/env python3
"""Build helper for the Factorio blueprint tools catalog webpage.

Validates the data files written by the sibling agents, refreshes the
``data/last_built.json`` stamp the front-end displays, and (optionally)
serves the static site for local preview.

Stdlib only. Run from the repo root:

    python3 webpage/build.py
    python3 webpage/build.py --serve --port 8000
"""

from __future__ import annotations

import argparse
import datetime as _dt
import http.server
import json
import socketserver
import sys
from pathlib import Path

REQUIRED_FIELDS = ("id", "name", "homepage", "category")
# A record must carry at least one prose field; surveys used either name.
DESCRIPTION_FIELDS = ("description", "summary")
KNOWN_CATEGORIES = {
    "visual-editor",
    "calculator",
    "string-paste",
    "renderer",
    "in-game-mod",
    "library",
    "compiler",
    "decoder",
    "transformer",
    "analyzer",
    "discord-bot",
    "spreadsheet",
    "reference-web",
}

# Data files we may find under webpage/data/.
DATA_FILES = (
    "oss_tools.json",
    "community_tools.json",
    "community_sentiment_oss.json",
)


def _load_records(path: Path) -> list[dict]:
    """Return a list of tool records from a JSON file.

    Accepts either a top-level array or a ``{"tools": [...]}`` wrapper.
    Returns ``[]`` for ``community_sentiment_oss.json`` style payloads
    that don't follow the tool-record schema.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if isinstance(raw.get("tools"), list):
            return raw["tools"]
        # Sentiment / ancillary payloads: nothing to validate against the
        # tool-record schema, but the file is still well-formed JSON.
        return []
    raise ValueError(f"{path.name}: unsupported top-level type {type(raw).__name__}")


def _validate_record(record: dict, idx: int, source: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return [f"{source}[{idx}]: record is not an object"]
    for field in REQUIRED_FIELDS:
        if field not in record or record[field] in (None, ""):
            errors.append(f"{source}[{idx}]: missing required field {field!r}")
    if not any(record.get(f) for f in DESCRIPTION_FIELDS):
        errors.append(
            f"{source}[{idx}]: needs one of {DESCRIPTION_FIELDS!r}"
        )
    cat = record.get("category")
    if cat and cat not in KNOWN_CATEGORIES:
        errors.append(
            f"{source}[{idx}] ({record.get('id', '?')}): unknown category {cat!r}"
        )
    return errors


def validate(data_dir: Path) -> tuple[dict[str, int], list[str], list[str]]:
    counts: dict[str, int] = {}
    warnings: list[str] = []
    errors: list[str] = []

    for name in DATA_FILES:
        path = data_dir / name
        if not path.exists():
            warnings.append(f"missing: {path.relative_to(data_dir.parent)}")
            counts[name] = 0
            continue
        try:
            records = _load_records(path)
        except json.JSONDecodeError as e:
            errors.append(f"{name}: invalid JSON: {e}")
            counts[name] = 0
            continue
        except ValueError as e:
            errors.append(str(e))
            counts[name] = 0
            continue

        counts[name] = len(records)
        # Only validate record schema for the tool list files.
        if name in ("oss_tools.json", "community_tools.json"):
            for i, rec in enumerate(records):
                errors.extend(_validate_record(rec, i, name))

    return counts, warnings, errors


def write_stamp(data_dir: Path, counts: dict[str, int]) -> Path:
    stamp = {
        "last_built": _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "counts": counts,
        "source": "webpage/build.py",
    }
    out = data_dir / "last_built.json"
    out.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return out


def serve(webpage_dir: Path, port: int) -> None:
    handler_cls = http.server.SimpleHTTPRequestHandler

    class _Handler(handler_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(webpage_dir), **kwargs)

        def log_message(self, fmt: str, *args) -> None:  # noqa: D401
            sys.stderr.write("[serve] " + fmt % args + "\n")

    with socketserver.TCPServer(("", port), _Handler) as httpd:
        print(f"serving {webpage_dir} on http://localhost:{port}/  (ctrl-c to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nshutting down")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--serve",
        action="store_true",
        help="after building, run python -m http.server-equivalent on the webpage dir",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port for --serve (default: 8000)",
    )
    args = parser.parse_args(argv)

    webpage_dir = Path(__file__).resolve().parent
    data_dir = webpage_dir / "data"
    data_dir.mkdir(exist_ok=True)

    counts, warnings, errors = validate(data_dir)

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)

    stamp_path = write_stamp(data_dir, counts)

    total_records = sum(counts.values())
    print(
        f"validated {total_records} record(s) across {len(DATA_FILES)} data file(s); "
        f"stamp written to {stamp_path.relative_to(webpage_dir.parent)}"
    )
    for name, n in counts.items():
        print(f"  {name}: {n}")

    if errors:
        return 2

    if args.serve:
        serve(webpage_dir, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
