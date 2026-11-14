#!/bin/bash
# Full build of the R36HD core: patches the upstream sources, compiles them with waf, links one libretro core.
#   tools/build.sh            -> build/hl_ship/halflife_libretro.so
#   tools/build.sh configure  -> also (re)runs the waf configure step (needed the first time)
set -e
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd $R
python3 tools/patch_sources.py | grep -v unchanged || true
if [ "${1:-}" = configure ] || [ ! -d build/hl_ship/engine/c4che ]; then
  rm -f third_party/xash3d-fwgs/.lock-waf_r36_ship third_party/hlsdk-portable/.lock-waf_r36_ship
  bash tools/waf_build.sh configure
fi
bash tools/waf_build.sh build | grep -vE 'libbacktrace|engine waf exit' || true
rm -f build/hl_ship/hlsdk/link_cmds.txt
python3 tools/link_core.py
bash tools/check_core.sh
