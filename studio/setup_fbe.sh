#!/usr/bin/env bash
# Install the Factorio Blueprint Editor (FBE) bundle into studio/static/fbe/
# so the studio can iframe a real sprite-rendered editor instead of falling
# back to the ASCII preview.
#
# What this does:
#   1. Pre-downloads the entry-point assets (index.html, JS, CSS, data.json,
#      transcoder, fonts, logo SVGs) from https://fbe.teoxoy.com so the first
#      iframe load doesn't have to round-trip per file.
#   2. Rewrites absolute URLs in HTML/JS/CSS so /data, /assets, /fonts, etc
#      become /fbe/data, /fbe/assets, /fbe/fonts (matching the studio_server
#      proxy mount point).
#
# Sprite atlases (~hundreds of small .basis textures under /data/__base__/
# graphics/...) are NOT pre-downloaded. The studio_server lazily proxies +
# caches them on first request, so they accumulate in studio/static/fbe/data/
# as you load blueprints. After warm-up the iframe needs no network access.
#
# Re-running this script overwrites the cached entry-point files (useful if
# upstream ships a new bundle hash); sprite cache is left intact.
#
# Disk usage:
#   - Entry-point bundle:    ~3 MB
#   - data.json:             ~2 MB
#   - Per blueprint sprites: ~100 KB - 5 MB (varies; cached forever)
#
# All of studio/static/fbe/ is gitignored.

set -euo pipefail

UPSTREAM="${FBE_UPSTREAM:-https://fbe.teoxoy.com}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HERE/static/fbe"

mkdir -p "$DEST"

err() { printf '[setup_fbe] %s\n' "$*" >&2; }
log() { printf '[setup_fbe] %s\n' "$*"; }

require() {
    if ! command -v "$1" >/dev/null 2>&1; then
        err "missing dependency: $1"
        exit 1
    fi
}

require curl
require sed

# Fetch the upstream HTML so we can extract the hashed asset filenames
# (e.g. assets/index-B6HcHAUD.js). Vite ships a new hash per build, so we
# must scrape rather than hardcode.
log "probing $UPSTREAM"
HTML="$(curl --fail --silent --show-error -L "$UPSTREAM/")" || {
    err "could not reach $UPSTREAM (offline? blocked?)"
    err "the studio will fall back to the ASCII preview until this succeeds."
    exit 2
}

# Save HTML last (after we have all referenced assets), so the presence of
# index.html doubles as our "FBE installed" sentinel for the studio_server
# health check.
JS_REL="$(  printf '%s\n' "$HTML" | grep -oE 'src="/assets/[^"]+\.js"'   | head -n1 | sed -E 's/src="\/?(.*)"/\1/')"
CSS_REL="$( printf '%s\n' "$HTML" | grep -oE 'href="/assets/[^"]+\.css"' | head -n1 | sed -E 's/href="\/?(.*)"/\1/')"

if [[ -z "$JS_REL" || -z "$CSS_REL" ]]; then
    err "could not find /assets/*.js or /assets/*.css in upstream HTML."
    err "did the bundle layout change? aborting."
    exit 3
fi
log "main JS:  $JS_REL"
log "main CSS: $CSS_REL"

# fetch_to <relative_url> <local_dest_relative_to_DEST>
fetch_to() {
    local url="$1"
    local out="$2"
    local target="$DEST/$out"
    mkdir -p "$(dirname "$target")"
    log "fetch /$url"
    if ! curl --fail --silent --show-error -L -o "$target.part" "$UPSTREAM/$url"; then
        err "  failed: $url"
        rm -f "$target.part"
        return 1
    fi
    mv "$target.part" "$target"
}

# Static assets referenced by the HTML.
fetch_to "$JS_REL"  "$JS_REL"
fetch_to "$CSS_REL" "$CSS_REL"
fetch_to "favicon.png"      "favicon.png"
fetch_to "logo.svg"         "logo.svg"
fetch_to "logo-small.svg"   "logo-small.svg"
fetch_to "loadingWheel.svg" "loadingWheel.svg"
fetch_to "discord.svg"      "discord.svg"
fetch_to "github.svg"       "github.svg"

# Mandatory runtime assets referenced by the JS.
fetch_to "data/data.json" "data/data.json"

# Transcoder (Basis Universal). Filenames change per upstream build; scrape
# them out of the JS.
JS_TEXT="$(cat "$DEST/$JS_REL")"
TR_JS="$(  printf '%s' "$JS_TEXT" | grep -oE '/assets/transcoder[^"]+\.js'   | head -n1)"
TR_WASM="$(printf '%s' "$JS_TEXT" | grep -oE '/assets/transcoder[^"]+\.wasm' | head -n1)"
if [[ -n "$TR_JS"   ]]; then fetch_to "${TR_JS#/}"   "${TR_JS#/}"; fi
if [[ -n "$TR_WASM" ]]; then fetch_to "${TR_WASM#/}" "${TR_WASM#/}"; fi

# Fonts referenced by CSS.
CSS_TEXT="$(cat "$DEST/$CSS_REL")"
while IFS= read -r font; do
    [[ -z "$font" ]] && continue
    fetch_to "${font#/}" "${font#/}"
done < <(printf '%s' "$CSS_TEXT" | grep -oE 'url\([^)]+\)' \
                                  | sed -E 's#^url\(([^)]+)\)$#\1#' \
                                  | tr -d "\"'" \
                                  | grep '^/fonts/')

# In-place URL rewrite so absolute upstream paths resolve under /fbe/.
# This MUST match _FBE_PATH_REWRITES in tools/studio_server.py.
rewrite_paths() {
    local f="$1"
    [[ -f "$f" ]] || return 0
    sed -i \
        -e 's#"/data/#"/fbe/data/#g' \
        -e "s#'/data/#'/fbe/data/#g" \
        -e 's#`/data/#`/fbe/data/#g' \
        -e 's#"/assets/#"/fbe/assets/#g' \
        -e "s#'/assets/#'/fbe/assets/#g" \
        -e 's#`/assets/#`/fbe/assets/#g' \
        -e 's#url(/fonts/#url(/fbe/fonts/#g' \
        -e 's#"/favicon.png"#"/fbe/favicon.png"#g' \
        -e 's#"/logo.svg"#"/fbe/logo.svg"#g' \
        -e 's#"/logo-small.svg"#"/fbe/logo-small.svg"#g' \
        -e 's#"/loadingWheel.svg"#"/fbe/loadingWheel.svg"#g' \
        -e 's#"/discord.svg"#"/fbe/discord.svg"#g' \
        -e 's#"/github.svg"#"/fbe/github.svg"#g' \
        "$f"
}

rewrite_paths "$DEST/$JS_REL"
rewrite_paths "$DEST/$CSS_REL"

# Save the patched HTML last so its presence is our installation sentinel.
# Strip the Cloudflare insights beacon (we don't ship analytics on loopback).
# Rewrite every href/src that points to a root-relative URL ("/foo") to
# "/fbe/foo". We only match attribute-quoted absolute paths so we don't
# accidentally rewrite link text. Skip values that already start with /fbe/.
log "writing patched index.html"
printf '%s' "$HTML" \
    | sed -E \
        -e 's#<script[^>]*cloudflareinsights[^<]*</script>##g' \
        -e 's#(href|src)="/(fbe/)#\1="/\2#g' \
        -e 's#(href|src)="/([^/"][^"]*)"#\1="/fbe/\2"#g' \
        -e "s#(href|src)='/(fbe/)#\\1='/\\2#g" \
        -e "s#(href|src)='/([^/'][^']*)'#\\1='/fbe/\\2'#g" \
    > "$DEST/index.html"

log "done. installed bundle in: $DEST"
log ""
log "Sizes:"
du -sh "$DEST" 2>/dev/null || true
log ""
log "Sprite atlases will be lazily proxied + cached on first iframe load."

# ---------------------------------------------------------------------------
# Mod-aware extension. The upstream FBE bundle only ships __base__ +
# __core__ prototypes (121 entities). Our user runs Factorio + Space Age +
# Quality + Elevated Rails + ~30 mods, which add foundry, recycler,
# electromagnetic-plant, biochamber, etc., and tweak vanilla parameters
# (AdjustableModule: beacon module_slots 2 -> 5, distribution_effectivity
# 1.5 -> 3, etc.).
#
# `tools/extend_fbe_for_mods.py` patches FBE's data.json to include every
# missing prototype and every modded parameter, then copies the matching
# PNG sprites out of the local Factorio install. It also patches the FBE
# JS bundle to load .png files directly (the upstream bundle expects
# Basis Universal -- we don't have basisu, and PixiJS supports PNG
# natively).
#
# Skip with FBE_NO_MOD_EXTEND=1 if you want a strict vanilla render
# (e.g. for parity testing against fbe.teoxoy.com).
# ---------------------------------------------------------------------------

if [[ -z "${FBE_NO_MOD_EXTEND:-}" ]]; then
    REPO_ROOT="$(cd -- "$HERE/.." && pwd)"
    EXT_SCRIPT="$REPO_ROOT/tools/extend_fbe_for_mods.py"
    DUMP="$REPO_ROOT/specs/data-raw-dump.json"
    if [[ -f "$EXT_SCRIPT" && -f "$DUMP" ]]; then
        log ""
        log "applying mod-aware extension..."
        if python3 "$EXT_SCRIPT" --quiet; then
            log "extension applied"
        else
            err "extension failed; bundle is still usable but won't render modded entities"
        fi
    elif [[ ! -f "$DUMP" ]]; then
        log ""
        log "skipping mod-aware extension: $DUMP not present."
        log "  To enable: run \`bash $REPO_ROOT/tools/dump_prototypes.sh\` then re-run this script."
    fi
else
    log ""
    log "FBE_NO_MOD_EXTEND set; skipping mod-aware extension."
fi

log ""
log "Start (or restart) the studio: python3 tools/studio_server.py --port 8766"
