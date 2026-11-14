#!/bin/bash
# Configures and compiles Xash3D FWGS and hlsdk-portable with waf for the R36HD (SF3000 GCC 6.3, hard float),
# so every object gets the defines waf would give it. Linking into one libretro core is done by tools/link_core.py.
#   waf_build.sh [configure|build|all]
set -u
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source $R/tools/env_ship.sh
STEP=${1:-all}
export CC="${SF_PREFIX}gcc" CXX="${SF_PREFIX}g++" AR="${SF_PREFIX}ar" LD="${SF_PREFIX}ld" OBJCOPY="${SF_PREFIX}objcopy" STRIP="${SF_PREFIX}strip"
ARCHF="-EL -mips32r2 -march=mips32r2 -mtune=74kc -mfp32 -mhard-float -mlong-calls --sysroot=$SF_SYSROOT -fPIC"
export CFLAGS="$ARCHF -O2 -DNDEBUG -DXASH_LIBRETRO=1 -I$R/src/libretro -include $R/src/libretro/fastmath.h"
export CXXFLAGS="$CFLAGS"
export LINKFLAGS="-EL -mips32r2 -mfp32 -mhard-float --sysroot=$SF_SYSROOT"
export LDFLAGS="$LINKFLAGS"
export LD_RELOCATABLE_FLAGS="-EL"
OUT=$R/build/hl_ship
mkdir -p $OUT
export WAFLOCK=.lock-waf_r36_ship
cd $R/third_party/xash3d-fwgs
if [ "$STEP" = configure ] || [ "$STEP" = all ]; then
  python3 waf configure -o $OUT/engine -T release --enable-fbdev --enable-soft --disable-gl --low-memory-mode=1 \
    --enable-bundled-deps --disable-werror --disable-utils-mdldec --disable-utils-xcf --disable-utils-xrcon-tui \
    --static-linking=filesystem_stdio,ref_soft,menu > $OUT/engine_configure.log 2>&1 || { echo "ENGINE CONFIGURE FAILED"; tail -40 $OUT/engine_configure.log; exit 1; }
  # static linking mode makes waf build static libraries without -fPIC; everything goes into one .so here
  find $OUT/engine/c4che -name '*.py' | xargs sed -i "s/\['-fno-PIC'\]/['-fPIC']/g"
  cd $R/third_party/hlsdk-portable
  python3 waf configure -o $OUT/hlsdk -T release --disable-werror > $OUT/hlsdk_configure.log 2>&1 || { echo "HLSDK CONFIGURE FAILED"; tail -40 $OUT/hlsdk_configure.log; exit 1; }
  find $OUT/hlsdk/c4che -name '*.py' | xargs sed -i "s/\['-fno-PIC'\]/['-fPIC']/g"
  cd $R/third_party/xash3d-fwgs
fi
if [ "$STEP" = build ] || [ "$STEP" = all ]; then
  python3 waf build -j${JOBS:-8} -k > $OUT/engine_build.log 2>&1; echo "engine waf exit $?"
  grep -E 'error' $OUT/engine_build.log | head -20
  cd $R/third_party/hlsdk-portable
  python3 waf build -j${JOBS:-8} -k > $OUT/hlsdk_build.log 2>&1; echo "hlsdk waf exit $?"
  grep -E 'error' $OUT/hlsdk_build.log | head -20
fi
