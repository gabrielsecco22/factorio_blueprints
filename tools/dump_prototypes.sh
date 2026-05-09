#!/usr/bin/env bash
# dump_prototypes.sh — regenerate specs/data-raw-dump.json from the user's
# current Factorio install + enabled mod set.
#
# Usage:
#   bash tools/dump_prototypes.sh             # run a real dump
#   bash tools/dump_prototypes.sh --dry-run   # print what would happen, change nothing
#
# Notes:
#   Factorio writes the dump to <user-data>/script-output/data-raw-dump.json.
#   We invoke `<binary> --dump-data`, then move/copy the result into specs/.

set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run|-n) DRY_RUN=1 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            echo "unknown arg: $arg" >&2
            exit 2
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DETECT="$SCRIPT_DIR/detect_factorio.py"
TARGET="$REPO_ROOT/specs/data-raw-dump.json"

if [[ ! -f "$DETECT" ]]; then
    echo "missing detector: $DETECT" >&2
    exit 1
fi

INFO_JSON="$(python3 "$DETECT")" || {
    echo "detect_factorio.py failed; cannot locate Factorio." >&2
    exit 1
}

# Pull the fields we need without bringing in jq.
read_field() {
    python3 -c "import json,sys; d=json.loads(sys.stdin.read()); \
v=d; \
[v:=v.get(k) for k in sys.argv[1].split('.')]; \
print('' if v is None else v)" "$1" <<<"$INFO_JSON"
}

BINARY="$(read_field binary)"
USER_DATA="$(read_field user_data_dir)"
VERSION="$(read_field version_info.version)"

if [[ -z "$BINARY" || -z "$USER_DATA" ]]; then
    echo "detector returned incomplete info; aborting." >&2
    echo "$INFO_JSON" >&2
    exit 1
fi

SCRIPT_OUTPUT="$USER_DATA/script-output"
DUMP_SOURCE="$SCRIPT_OUTPUT/data-raw-dump.json"

echo "Factorio binary : $BINARY"
echo "User data dir   : $USER_DATA"
echo "Version         : ${VERSION:-unknown}"
echo "Dump source     : $DUMP_SOURCE"
echo "Dump target     : $TARGET"

if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] would run: \"$BINARY\" --dump-data"
    echo "[dry-run] would copy \"$DUMP_SOURCE\" -> \"$TARGET\""
    echo "[dry-run] no changes made."
    exit 0
fi

mkdir -p "$(dirname "$TARGET")"

echo "Running Factorio --dump-data ..."
"$BINARY" --dump-data >/dev/null

if [[ ! -f "$DUMP_SOURCE" ]]; then
    echo "expected dump file not found at $DUMP_SOURCE" >&2
    exit 1
fi

cp "$DUMP_SOURCE" "$TARGET"

# Summary line.
SIZE_BYTES="$(stat -c%s "$TARGET" 2>/dev/null || stat -f%z "$TARGET")"
SIZE_MB="$(python3 -c "print(round(${SIZE_BYTES}/1024/1024, 1))")"
SUMMARY="$(python3 - "$TARGET" "$USER_DATA" <<'PY'
import json, sys, pathlib
target = sys.argv[1]
user_data = pathlib.Path(sys.argv[2])
with open(target) as f:
    d = json.load(f)
categories = len(d)
mod_list = user_data / "mods" / "mod-list.json"
mods = "?"
if mod_list.is_file():
    ml = json.loads(mod_list.read_text())
    mods = sum(1 for m in ml.get("mods", []) if m.get("enabled"))
print(f"{categories} prototype categories, {mods} mods enabled")
PY
)"

echo "Wrote $TARGET (${SIZE_MB} MB; ${SUMMARY})"
