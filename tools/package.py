#!/usr/bin/env python3
"""Builds the TreeFrogUI port folder for Half-Life in dist/halflife (core, launcher script, config; no game files).

    python3 tools/package.py

Run after tools/build.sh. The core is stripped of debug information with the toolchain's own strip.
"""
import json, os, re, shutil, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID = "halflife"
CONTENT = "Start Half-Life.hl"
CORE_SRC = os.path.join(ROOT, "build", "hl_ship", f"{ID}_libretro.so")
EXTRAS = os.path.join(ROOT, "build", "hl_ship", "engine", "3rdparty", "extras", "extras.pk3")
STRIP = "/opt/toolchains/sf3000/mipsel-buildroot-linux-gnu_sdk-buildroot/opt/ext-toolchain/bin/mips-mti-linux-gnu-strip"

RUN_SH = """#!/bin/sh
set -eu
PORT_DIR=/mnt/sdcard/roms/ports/halflife
cd "$PORT_DIR"
rm -f /mnt/sdcard/cubegm/port_error.txt
if [ ! -f "$PORT_DIR/valve/halflife.wad" ] || [ ! -d "$PORT_DIR/valve/maps" ]; then
    echo "Half-Life data missing: copy your own Half-Life valve folder to $PORT_DIR/valve" > /mnt/sdcard/cubegm/port_error.txt
    exit 0
fi
if [ ! -f "$PORT_DIR/valve/skill.cfg" ]; then
    echo "valve/skill.cfg missing: this is the 25th anniversary data. Use the pre-25 Half-Life files (Steam beta steam_legacy)" > /mnt/sdcard/cubegm/port_error.txt
    exit 0
fi
exec /mnt/sdcard/cubegm/picoarch "$PORT_DIR/halflife_libretro.so" "$PORT_DIR/Start Half-Life.hl"
"""


def write_lf(path, text):
    with open(path, "w", newline="\n") as f:
        f.write(text)


def main():
    dst = os.path.join(ROOT, "dist", ID)
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.join(dst, "valve"))
    core = os.path.join(dst, f"{ID}_libretro.so")
    subprocess.run([STRIP, "--strip-debug", "-o", core, CORE_SRC], check=True)
    # the compiler leaves the build folder in file names it embeds for messages: cut that prefix off in place
    # (same length, the rest of each string is kept, so every pointer stays valid)
    prefix = (ROOT.replace("\\", "/") + "/").encode()
    data = open(core, "rb").read()
    data = re.sub(re.escape(prefix) + rb"([^\0]*)", lambda m: m.group(1) + b"\0" * len(prefix), data)
    open(core, "wb").write(data)
    write_lf(os.path.join(dst, CONTENT), "Half-Life\n")
    write_lf(os.path.join(dst, "run.sh"), RUN_SH)
    cfg = {
        "schema_version": 1, "id": ID, "name": "Half-Life", "launcher": "Half-Life.sh",
        "launch": {"type": "libretro", "binary": f"{ID}_libretro.so", "content": CONTENT},
        "required_file_sets": [["valve/halflife.wad", "valve/maps/c1a0.bsp", "valve/skill.cfg"]],
        "setup_guide": f"docs/setup/{ID}.md",
    }
    write_lf(os.path.join(dst, "config.json"), json.dumps(cfg, indent=2) + "\n")
    write_lf(os.path.join(dst, ".requires_game_data"), "valve/ from your own copy of Half-Life\n")
    shutil.copyfile(EXTRAS, os.path.join(dst, "valve", "extras.pk3"))   # menu art, built from the engine source (GPL)
    print("port folder:", dst)


main()
