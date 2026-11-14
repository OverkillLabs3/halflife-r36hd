# Building

The core is cross-compiled on Linux (or WSL2 on Windows) with the SF3000 toolchain: GCC 6.3, glibc 2.20,
MIPS32r2 hard float, the same toolchain the system's own cores use.

## Requirements

- Linux or WSL2 (Ubuntu 22.04 or newer)
- `git`, `python3`, `curl`, `make`

## Steps

```sh
bash tools/get_toolchain.sh      # downloads the toolchain to /opt/toolchains/sf3000
bash tools/fetch_sources.sh      # pinned Xash3D FWGS and hlsdk-portable into third_party/
bash tools/build.sh configure    # first build; later builds: bash tools/build.sh
python3 tools/package.py         # SD-card folder in dist/halflife
```

`build/hl_ship/halflife_libretro.so` is the core. `tools/check_core.sh` prints its ISA, float ABI, needed
libraries and newest glibc symbol (must be 2.20 or older).

## Layout

| Path | What |
|---|---|
| `src/libretro/` | libretro front end: video, sound and pad backends for the engine, core options, FPS counter |
| `tools/patch_sources.py` | patches applied to the upstream engine and SDK (renderer speed, memory, device fixes); idempotent |
| `tools/waf_build.sh` | waf configure and build of both upstream trees for the device |
| `tools/link_core.py` | links engine, renderer, menu, server and client into one libretro core |
| `tools/package.py` | builds the TreeFrogUI port folder |

The engine, renderer, menu and both game libraries are linked into one shared object. Each library keeps its
own symbol names (prefixed at link time), and the engine finds them through a built-in table instead of
`dlopen`.
