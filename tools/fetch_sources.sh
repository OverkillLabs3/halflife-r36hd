#!/bin/bash
# Fetches the pinned upstream engine and game SDK into third_party/.
set -e
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p $R/third_party && cd $R/third_party
[ -d xash3d-fwgs ] || git clone --recursive https://github.com/FWGS/xash3d-fwgs.git
(cd xash3d-fwgs && git checkout 707596f4905689ec224e993fcaa4d4ad66aa67d6 && git submodule update --init --recursive)
[ -d hlsdk-portable ] || git clone --recursive https://github.com/FWGS/hlsdk-portable.git
(cd hlsdk-portable && git checkout 89e83b92d561f5ceb11594c2f15e2e1519bc6c36 && git submodule update --init --recursive)
