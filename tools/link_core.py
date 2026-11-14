#!/usr/bin/env python3
"""Link Half-Life (Xash3D FWGS engine + filesystem + ref_soft + mainui + hlsdk server + client) into one
libretro core, halflife_libretro.so. Objects come from waf (tools/waf_build.sh). Run on Linux or WSL:
    python3 tools/link_core.py        -> build/hl_ship/halflife_libretro.so

Each sub-library is first linked into one relocatable object (ld -r) with an export table lib_<name>_exports
(what COM_LoadLibrary/COM_GetProcAddress look up, platform/misc/lib_static.c). Then every symbol it defines,
except that table, is renamed to <name>__<symbol>, so the libraries cannot clash with each other or with the
engine. (waf's own method makes them local with objcopy -G, which MIPS PIC code cannot link: CALL16 relocations
must point at global symbols.)
"""
import os, re, subprocess, sys, ast, glob, shlex

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAT = "ship"
os.environ["WAFLOCK"] = f".lock-waf_r36_{PLAT}"   # same as tools/waf_build.sh
B = f"{R}/build/hl_{PLAT}"
ENG = f"{B}/engine"
SDK = f"{B}/hlsdk"
OUT = f"{B}/link"
os.makedirs(OUT, exist_ok=True)

SF = "/opt/toolchains/sf3000/mipsel-buildroot-linux-gnu_sdk-buildroot"
P = f"{SF}/opt/ext-toolchain/bin/mips-mti-linux-gnu-"
SYSROOT = f"{SF}/mipsel-buildroot-linux-gnu/sysroot"
ARCH = ["-EL", "-mips32r2", "-march=mips32r2", "-mtune=74kc", "-mfp32", "-mhard-float", "-mlong-calls", f"--sysroot={SYSROOT}", "-fPIC"]
CC = [P + "gcc"] + ARCH
CXX = [P + "g++"] + ARCH
LD = [P + "ld", "-EL"]
NM = P + "nm"
OBJCOPY = P + "objcopy"
LDSHARED = [P + "g++", "-EL", "-mips32r2", "-mfp32", "-mhard-float", f"--sysroot={SYSROOT}", "-shared"]

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd)[:400])
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit(1)
    return r.stdout

def defined_globals(obj):
    out = run([NM, "-g", "--defined-only", obj])
    syms = []
    for l in out.splitlines():
        f = l.split()
        if len(f) >= 3:
            syms.append((f[1], f[2]))
    return syms

def rename_defined(obj_in, obj_out, prefix, keep):
    syms = defined_globals(obj_in)
    m = f"{OUT}/{prefix}.redefine"
    with open(m, "w") as f:
        for t, s in syms:
            if s in keep:
                continue
            f.write(f"{s} {prefix}__{s}\n")
    run([OBJCOPY, f"--redefine-syms={m}", obj_in, obj_out])

# ---- the game libraries from hlsdk: object lists from waf's verbose link commands
def sdk_link_lists():
    log = f"{SDK}/link_cmds.txt"
    if not os.path.exists(log):
        for so in glob.glob(f"{SDK}/dlls/*.so") + glob.glob(f"{SDK}/cl_dll/*.so"):
            os.remove(so)
        r = subprocess.run(["python3", "waf", "build", "-k", "-v"], cwd=f"{R}/third_party/hlsdk-portable", capture_output=True, text=True)
        with open(log, "w") as f:
            f.write(r.stdout + r.stderr)
    lists = {}
    for line in open(log):
        if "runner [" not in line or "-shared" not in line:
            continue
        cmd = ast.literal_eval(line[line.index("runner [") + 7:].strip())
        outp = next((c[2:] for c in cmd if c.startswith("-o") and len(c) > 2), "")
        objs = [os.path.normpath(os.path.join(SDK, c)) if not c.startswith("/") else c for c in cmd if c.endswith(".o")]
        ldirs = [os.path.normpath(os.path.join(SDK, c[2:])) for c in cmd if c.startswith("-L")]
        archives = []
        for c in cmd:
            if c.startswith("-l") and c not in ("-lm", "-ldl", "-lpthread", "-lrt", "-lc"):
                for d in ldirs:
                    a = os.path.join(d, f"lib{c[2:]}.a")
                    if os.path.exists(a):
                        archives.append(a); break
        name = "server" if "/dlls/" in outp else "client"
        lists[name] = (objs, archives)
    return lists

def cxx_exports(obj):
    # every defined, unmangled function: entity classes (LINK_ENTITY_TO_CLASS), GetEntityAPI, Initialize, HUD_*, F ...
    ex = []
    for t, s in defined_globals(obj):
        if t in "TtW" and not s.startswith("_") and re.match(r"^[A-Za-z][A-Za-z0-9_]*$", s):
            ex.append(s)
    return sorted(set(ex))

def make_lib(name, objs, extra):
    raw = f"{OUT}/{name}_raw.o"
    run(LD + ["-r", "-o", raw] + objs + extra)
    exports = cxx_exports(raw)
    helper = f"{OUT}/{name}_exports.c"
    with open(helper, "w") as f:
        f.write("".join(f"extern void {e}(void);\n" for e in exports))
        f.write(f"struct {{ const char *name; void *func; }} lib_{name}_exports[] = {{\n")
        f.write("".join(f'\t{{ "{e}", (void *)&{e} }},\n' for e in exports))
        f.write("\t{ 0, 0 }\n};\n")
    run(CC + ["-O1", "-w", "-c", helper, "-o", helper + ".o"])
    full = f"{OUT}/{name}_full.o"
    run(LD + ["-r", "-o", full, raw, helper + ".o"])
    final = f"{OUT}/{name}.o"
    rename_defined(full, final, name, {f"lib_{name}_exports"})
    print(f"{name}: {len(objs)} objects, {len(exports)} exports")
    return final

parts = []
sdk = sdk_link_lists()
for name in ("server", "client"):
    objs, archives = sdk[name]
    parts.append(make_lib(name, objs, archives))

# ---- waf-made relocatables of the engine side libraries (already contain lib_<name>_exports)
# their private static libraries go inside them (ref_common belongs to the renderer); public/zlib are shared
for name, path, private in (("filesystem_stdio", f"{ENG}/filesystem/filesystem_stdio.unstripped.o", []),
                   ("ref_soft", f"{ENG}/ref/soft/ref_soft.unstripped.o", [f"{ENG}/ref/common/libref_common.a"]),
                   ("menu", f"{ENG}/3rdparty/mainui/menu.unstripped.o", [])):
    # waf's export table lists only part of what the engine asks for (no CreateInterface in filesystem_stdio):
    # rename it out of the way and build a full one like for the game libraries
    src = f"{OUT}/{name}_waf.o"
    run([OBJCOPY, f"--redefine-sym=lib_{name}_exports=lib_{name}_waf_exports", path, src])
    parts.append(make_lib(name, [src], private))

# ---- engine objects (without the fbdev/alsa/evdev platform files, replaced by src/libretro)
skip = ("vid_fbdev.c", "s_alsa.c", "in_evdev.c", "lib_static.c")
eng = sorted(o for o in glob.glob(f"{ENG}/engine/**/*.o", recursive=True) if not any(s in o for s in skip))

# compile flags of an engine source: taken from waf's cache of a known object (c4che env)
def engine_cflags():
    cache = f"{ENG}/engine_cflags.txt"
    if os.path.exists(cache):
        return open(cache).read().split("\n")
    # waf rebuilds by content hash: change the file to make it print the command
    p = f"{R}/third_party/xash3d-fwgs/engine/platform/misc/lib_static.c"
    t = open(p).read()
    open(p, "w").write(t + "\n" if not t.endswith("\n\n") else t.rstrip("\n") + "\n")
    r = subprocess.run(["python3", "waf", "build", "-k", "-v"], cwd=f"{R}/third_party/xash3d-fwgs", capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if "runner [" in line and "lib_static.c" in line and "-c" in line:
            cmd = ast.literal_eval(line[line.index("runner [") + 7:].strip())
            flags = [c for c in cmd[1:] if c.startswith(("-I", "-D", "-std", "-f", "-m", "-O", "-E", "--sysroot", "-W", "-g"))]
            # waf gives include paths relative to the build directory
            flags = [("-I" + os.path.normpath(os.path.join(ENG, c[2:]))) if c.startswith("-I") and not c[2:].startswith("/") else c for c in flags]
            open(cache, "w").write("\n".join(flags))
            return flags
    print("could not find the engine compile flags"); sys.exit(1)

EFLAGS = [f for f in engine_cflags() if f and not f.startswith("-W")] + ["-w", "-I" + f"{R}/src/libretro"]

# library table: the three waf libraries plus the two game libraries
with open(f"{OUT}/generated_library_tables.h", "w") as f:
    names = ["filesystem_stdio", "ref_soft", "menu", "server", "client"]
    f.write("".join(f"extern table_t lib_{n}_exports[];\n" for n in names))
    f.write("struct {const char *name;void *func;} libs[] = {\n")
    f.write("".join(f'{{ "{n}", &lib_{n}_exports }},\n' for n in names))
    f.write("{0,0}\n};\n")

lr = []
for src in ["vid_libretro.c", "s_libretro.c", "in_libretro.c", "hl_core.c"]:
    o = f"{OUT}/lr_{src}.o"
    vis = ["-fvisibility=default"] if src == "hl_core.c" else []   # retro_* must be exported
    run(CC + EFLAGS + vis + ["-O2", "-c", f"{R}/src/libretro/{src}", "-o", o])
    lr.append(o)
o = f"{OUT}/lib_static.o"
run(CC + ["-I" + OUT] + EFLAGS + ["-O2", "-c", f"{R}/src/libretro/lib_static_lr.c", "-o", o])   # our table first
lr.append(o)

static_libs = [f"{ENG}/public/libpublic.a", f"{ENG}/public/libbuild_vcs.a", f"{ENG}/3rdparty/miniz/libminiz.a",
    f"{ENG}/3rdparty/bzip2/libbzip2.a", f"{ENG}/3rdparty/mpg123/libmpg123.a", f"{ENG}/3rdparty/opusfile/libopusfile.a",
    f"{ENG}/3rdparty/opus/libopus.a", f"{ENG}/3rdparty/vorbis/libvorbisfile.a", f"{ENG}/3rdparty/vorbis/libvorbis.a",
    f"{ENG}/3rdparty/libogg/libogg.a", f"{ENG}/3rdparty/mbedtls/libmbedtls.a", f"{ENG}/3rdparty/MultiEmulator/libMultiEmulator.a",
    f"{ENG}/3rdparty/library_suffix/liblibrary_suffix.a", f"{ENG}/3rdparty/libbacktrace/libbacktrace_custom.a"]
so = f"{B}/halflife_libretro.so"
if os.path.exists(so):
    os.remove(so)
r = subprocess.run(LDSHARED + ["-o", so] + eng + lr + parts + ["-Wl,--start-group"] + static_libs + ["-Wl,--end-group",
    "-lm", "-lpthread", "-ldl", "-lrt", "-Wl,--no-undefined"], capture_output=True, text=True)
if r.returncode != 0:
    und = re.findall(r"undefined reference to `([^']+)'", r.stderr)
    from collections import Counter
    print("LINK FAILED")
    for s, n in Counter(und).most_common(40):
        print(f"  {n:4d} {s}")
    print(r.stderr[-2500:])
    sys.exit(1)
print("linked", so, os.path.getsize(so))
