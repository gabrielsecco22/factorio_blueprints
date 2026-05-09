#!/usr/bin/env python3
"""
detect_factorio.py — locate a Factorio install + user data dir, parse version
and enabled mods, and report whether Space Age is active.

Stdlib only. Works on Linux, macOS, and Windows.

CLI:
    python3 detect_factorio.py            # JSON to stdout
    python3 detect_factorio.py --human    # human-readable summary

Exit codes:
    0  install detected
    1  no install found
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Candidate path tables
# ---------------------------------------------------------------------------

def _expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


def _install_candidates() -> list[Path]:
    """Likely install directories (containing bin/, data/, etc.)."""
    system = platform.system()
    cands: list[Path] = []

    if system == "Linux":
        cands += [
            _expand("~/.steam/steam/steamapps/common/Factorio"),
            _expand("~/.local/share/Steam/steamapps/common/Factorio"),
            _expand("~/.var/app/com.valvesoftware.Steam/.local/share/Steam/"
                    "steamapps/common/Factorio"),
            _expand("~/snap/steam/common/.local/share/Steam/steamapps/common/Factorio"),
            _expand("/opt/factorio"),
            _expand("~/factorio"),
            _expand("~/Games/factorio"),
        ]
    elif system == "Darwin":
        cands += [
            _expand("~/Library/Application Support/Steam/steamapps/common/Factorio/"
                    "factorio.app/Contents"),
            _expand("/Applications/factorio.app/Contents"),
        ]
    elif system == "Windows":
        cands += [
            _expand(r"%ProgramFiles(x86)%\Steam\steamapps\common\Factorio"),
            _expand(r"%ProgramFiles%\Steam\steamapps\common\Factorio"),
            _expand(r"C:\Program Files (x86)\Steam\steamapps\common\Factorio"),
            _expand(r"C:\Program Files\Factorio"),
        ]
    return cands


def _user_data_candidates() -> list[Path]:
    """Likely user data directories (containing mods/, saves/, config/)."""
    system = platform.system()
    cands: list[Path] = []

    if system == "Linux":
        cands += [
            _expand("~/.factorio"),
            _expand("~/.var/app/com.valvesoftware.Steam/.factorio"),
        ]
    elif system == "Darwin":
        cands += [
            _expand("~/Library/Application Support/factorio"),
        ]
    elif system == "Windows":
        cands += [
            _expand(r"%APPDATA%\Factorio"),
        ]
    # Some installs are "standalone": user data sits inside the install dir.
    # Those are picked up indirectly via the install candidates below.
    return cands


def _binary_relpaths() -> list[str]:
    if platform.system() == "Windows":
        return ["bin/x64/factorio.exe", "bin/Win32/factorio.exe"]
    if platform.system() == "Darwin":
        return ["MacOS/factorio", "bin/x64/factorio"]
    return ["bin/x64/factorio", "bin/i386/factorio"]


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def find_install_dir() -> Optional[Path]:
    for c in _install_candidates():
        if not c.exists():
            continue
        for rel in _binary_relpaths():
            if (c / rel).is_file():
                return c
    return None


def find_binary(install_dir: Path) -> Optional[Path]:
    for rel in _binary_relpaths():
        p = install_dir / rel
        if p.is_file():
            return p
    return None


def find_user_data_dir(install_dir: Optional[Path]) -> Optional[Path]:
    for c in _user_data_candidates():
        if (c / "mods").is_dir() or (c / "config").is_dir():
            return c
    # Standalone install: user data may live inside install dir.
    if install_dir and (install_dir / "mods").is_dir():
        return install_dir
    return None


_VERSION_RE = re.compile(r"Version:\s*([\d.]+)\s*\(build\s*(\d+),\s*([^,)]+)")


def parse_version(binary: Path) -> dict:
    """Run `factorio --version` and parse the first line."""
    info: dict = {"version": None, "build": None, "platform": None, "raw": None}
    try:
        out = subprocess.run(
            [str(binary), "--version"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        info["error"] = f"failed to run binary: {e}"
        return info
    text = (out.stdout or "") + (out.stderr or "")
    info["raw"] = text.strip().splitlines()[0] if text.strip() else None
    m = _VERSION_RE.search(text)
    if m:
        info["version"] = m.group(1)
        info["build"] = int(m.group(2))
        info["platform"] = m.group(3).strip()
    return info


def parse_mod_list(user_data: Path) -> dict:
    """Parse mod-list.json. Returns {'all': [...], 'enabled': [...]}."""
    out = {"all": [], "enabled": [], "path": None}
    p = user_data / "mods" / "mod-list.json"
    if not p.is_file():
        return out
    out["path"] = str(p)
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        out["error"] = f"failed to read mod-list.json: {e}"
        return out
    for entry in data.get("mods", []):
        name = entry.get("name")
        if not name:
            continue
        out["all"].append(name)
        if entry.get("enabled"):
            out["enabled"].append(name)
    return out


_DLC_MODS = {"space-age", "quality", "elevated-rails"}


def detect() -> dict:
    install = find_install_dir()
    if install is None:
        return {"found": False, "reason": "no Factorio install located"}
    binary = find_binary(install)
    user_data = find_user_data_dir(install)
    info: dict = {
        "found": True,
        "install_dir": str(install),
        "binary": str(binary) if binary else None,
        "user_data_dir": str(user_data) if user_data else None,
        "platform": platform.system(),
    }
    if binary:
        info["version_info"] = parse_version(binary)
    if user_data:
        mods = parse_mod_list(user_data)
        info["mods"] = mods
        enabled = set(mods["enabled"])
        info["dlc"] = {
            "space_age": "space-age" in enabled,
            "quality": "quality" in enabled,
            "elevated_rails": "elevated-rails" in enabled,
        }
        third_party = [m for m in mods["enabled"]
                       if m != "base" and m not in _DLC_MODS]
        info["third_party_mod_count"] = len(third_party)
    return info


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _human(info: dict) -> str:
    if not info.get("found"):
        return f"Factorio not found: {info.get('reason', 'unknown')}"
    lines = [
        "Factorio detected",
        f"  install dir   : {info['install_dir']}",
        f"  binary        : {info['binary']}",
        f"  user data dir : {info['user_data_dir']}",
        f"  platform      : {info['platform']}",
    ]
    v = info.get("version_info") or {}
    if v.get("version"):
        lines.append(f"  version       : {v['version']} (build {v['build']}, {v['platform']})")
    elif v.get("error"):
        lines.append(f"  version       : <error: {v['error']}>")
    dlc = info.get("dlc") or {}
    if dlc:
        flag = lambda b: "yes" if b else "no"
        lines.append(
            f"  Space Age     : {flag(dlc['space_age'])}   "
            f"Quality: {flag(dlc['quality'])}   "
            f"Elevated Rails: {flag(dlc['elevated_rails'])}"
        )
    mods = info.get("mods") or {}
    if mods:
        lines.append(f"  mods enabled  : {len(mods['enabled'])} of {len(mods['all'])}")
        lines.append(f"  third-party   : {info.get('third_party_mod_count', 0)}")
    return "\n".join(lines)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Detect a Factorio install.")
    parser.add_argument("--human", action="store_true",
                        help="human-readable summary instead of JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    info = detect()
    if args.human:
        print(_human(info))
    else:
        print(json.dumps(info, indent=2, sort_keys=True))
    return 0 if info.get("found") else 1


if __name__ == "__main__":
    sys.exit(main())
