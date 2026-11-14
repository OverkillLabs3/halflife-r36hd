#!/bin/bash
# Downloads the official TreeFrogUI/SF3000 hard-float glibc toolchain into /opt/toolchains/sf3000.
set -e
sudo mkdir -p /opt/toolchains/sf3000
sudo chown "$(id -un)" /opt/toolchains/sf3000
cd /opt/toolchains/sf3000
URL=https://github.com/game-de-it/sf3000/releases/download/sf3000_toolchain_v0.1/mipsel-buildroot-linux-gnu_sdk-buildroot.tar.gz
[ -f tc.tar.gz ] || curl -fsSL --retry 3 -o tc.tar.gz "$URL"
ls -la tc.tar.gz
[ -d mipsel-buildroot-linux-gnu_sdk-buildroot ] || tar xzf tc.tar.gz
ls
