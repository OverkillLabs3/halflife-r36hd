#!/bin/bash
# Checks for the shipped Half-Life core: ISA, float ABI, needed libraries, newest glibc symbol, section sizes.
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source $R/tools/env_ship.sh
SO=${1:-$R/build/hl_ship/halflife_libretro.so}
${SF_PREFIX}readelf -A $SO 2>/dev/null | grep -E 'ISA:|FP ABI'
${SF_PREFIX}readelf -d $SO | grep NEEDED
echo "newest GLIBC symbol version: $(${SF_PREFIX}objdump -T $SO | grep -o 'GLIBC_[0-9.]*' | sort -t. -k1,1 -k2,2n -k3,3n -V | uniq | tail -1)"
echo "newest GLIBCXX: $(${SF_PREFIX}objdump -T $SO | grep -o 'GLIBCXX_[0-9.]*' | sort -V | uniq | tail -1)  CXXABI: $(${SF_PREFIX}objdump -T $SO | grep -o 'CXXABI_[0-9.]*' | sort -V | uniq | tail -1)"
${SF_PREFIX}size $SO
${SF_PREFIX}nm -D --defined-only $SO | grep ' retro_' | wc -l
head -c 6 $SO | od -An -tx1
