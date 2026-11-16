#!/bin/bash
# Builds the three helpers in tweaks/ with the console's toolchain (tools/get_toolchain.sh installs it).
#   tools/build_tweaks.sh   -> build/tweaks/{libr36mem.so,tlbclear,sdfast}
set -e
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SF=/opt/toolchains/sf3000/mipsel-buildroot-linux-gnu_sdk-buildroot
CC=$SF/opt/ext-toolchain/bin/mips-mti-linux-gnu-gcc
SR=$SF/mipsel-buildroot-linux-gnu/sysroot
FLAGS="-EL -mips32r2 -march=mips32r2 -mfp32 -mhard-float --sysroot=$SR -O2 -Wall"
O=$R/build/tweaks
mkdir -p "$O"
$CC $FLAGS -fPIC -shared -o "$O/libr36mem.so" "$R/tweaks/fastmem.c" -ldl
$CC $FLAGS -o "$O/tlbclear" "$R/tweaks/tlbclear.c"
$CC $FLAGS -o "$O/sdfast" "$R/tweaks/sdfast.c"
ls -la "$O"
