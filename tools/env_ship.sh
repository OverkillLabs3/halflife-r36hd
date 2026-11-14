# Source this file: sets up the R36HD ship toolchain (hard-float glibc).
export SF_ROOT=/opt/toolchains/sf3000/mipsel-buildroot-linux-gnu_sdk-buildroot
export SF_PREFIX=$SF_ROOT/opt/ext-toolchain/bin/mips-mti-linux-gnu-
export SF_SYSROOT=$SF_ROOT/mipsel-buildroot-linux-gnu/sysroot
export SF_CFLAGS="-EL -mips32r2 -march=mips32r2 -mfp32 -mhard-float -mlong-calls --sysroot=$SF_SYSROOT -fPIC -O3 -DNDEBUG"
export SF_LDFLAGS="-EL -mips32r2 -mfp32 -mhard-float --sysroot=$SF_SYSROOT"
export QEMU_RUN="qemu-mipsel -L $SF_SYSROOT"
