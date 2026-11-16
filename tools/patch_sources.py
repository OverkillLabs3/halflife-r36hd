"""Idempotent patches to the Xash3D FWGS checkout for the R36HD libretro core (src/libretro).
Run from the repository root: python3 tools/patch_sources.py
All changes are under XASH_LIBRETRO, so the tree still builds for other targets.
"""
import pathlib

root = pathlib.Path("third_party/xash3d-fwgs")

def patch(rel, fn):
    p = root / rel
    raw = p.read_bytes()
    crlf = b"\r\n" in raw
    t = raw.decode("utf-8").replace("\r\n", "\n")
    new = fn(t)
    if new == t:
        print("unchanged", rel)
        return
    if crlf:
        new = new.replace("\n", "\r\n")
    p.write_bytes(new.encode("utf-8"))
    print("patched  ", rel)

def write(rel, text):
    p = root / rel
    if p.exists() and p.read_text() == text:
        print("unchanged", rel)
        return
    p.write_text(text)
    print("written  ", rel)

# 1. main loop: hand control to retro_run once per iteration
def host(t):
    if "XASH_LIBRETRO" in t:
        return t
    old = "\twhile( host.status != HOST_CRASHED )\n\t{\n\t\tdouble newtime = Platform_DoubleTime();\n\t\tCOM_Frame( newtime - oldtime );\n\t\toldtime = newtime;\n\t}"
    assert old in t
    t = t.replace(old,
        "\twhile( host.status != HOST_CRASHED )\n\t{\n#if XASH_LIBRETRO\n\t\tLR_Sync();\n#endif\n"
        "\t\tdouble newtime = Platform_DoubleTime();\n\t\tCOM_Frame( newtime - oldtime );\n\t\toldtime = newtime;\n\t}", 1)
    t = t.replace('#include "platform/platform.h"\n', '#include "platform/platform.h"\n#if XASH_LIBRETRO\n#include "hl_libretro.h"\n#endif\n', 1)
    return t
patch("engine/common/host.c", host)

# 2. 22050 Hz mixing (HL sounds are 11 and 22 kHz; half the mixing work of 44.1 kHz)
def sound_h(t):
    if "XASH_LIBRETRO" in t:
        return t
    old = "#define SOUND_DMA_SPEED SOUND_44k // hardware playback rate"
    assert old in t
    return t.replace(old, "#if XASH_LIBRETRO\n#define SOUND_DMA_SPEED SOUND_22k // libretro core: 22050 Hz\n#else\n" + old + "\n#endif", 1)
patch("engine/client/sound.h", sound_h)

# 3. the soft renderer has no export list for static linking (ref_gl has one)
write("ref/soft/exports.txt", "GetRefAPI\n")

# 5. memory: fewer temp entities and edicts by default (single player on 19 MB), clamped after liblist/gameinfo
def gameinfo(t):
    if "XASH_LIBRETRO" in t:
        return t
    old = "\tGameInfo->max_tents      = 500;\n"
    assert old in t
    t = t.replace(old, "#if XASH_LIBRETRO\n\tGameInfo->max_tents      = 160; // libretro core: ~1 MB less than 500\n#else\n" + old + "#endif\n", 1)
    return t
patch("filesystem/gameinfo.c", gameinfo)

# (temp entity count: set in gameinfo.c below)

def defaults_h(t):
    if "XASH_LIBRETRO" in t:
        return t
    old = "#ifndef DEFAULT_MAX_EDICTS\n"
    assert old in t
    return t.replace(old, "#if XASH_LIBRETRO && !defined( DEFAULT_MAX_EDICTS )\n\t#define DEFAULT_MAX_EDICTS 900 // GoldSrc's value before HL25\n#endif\n" + old, 1)
patch("common/defaults.h", defaults_h)

# 6. memory: 16 entries of position history per entity instead of 64 (single player, loopback); the client
#    library is built from the same header change, so the struct layout matches
def history(t):
    if "HISTORY_MAX\t\t16" in t:
        return t
    old = "#define HISTORY_MAX\t\t64\t\t// Must be power of 2"
    assert old in t, "history"
    return t.replace(old, "#define HISTORY_MAX\t\t16\t\t// Must be power of 2 (R36HD: 16, was 64)", 1)
patch("common/cl_entity.h", history)
p = pathlib.Path("third_party/hlsdk-portable/common/cl_entity.h")
t = p.read_text(encoding="latin-1").replace("\r\n", "\n")
if "HISTORY_MAX\t\t16" not in t:
    import re as _re
    n = _re.sub(r"#define HISTORY_MAX\s+64", "#define HISTORY_MAX\t\t16", t, count=1)
    assert n != t, "hlsdk history"
    p.write_text(n, encoding="latin-1"); print("patched   hlsdk-portable/common/cl_entity.h")
else:
    print("unchanged hlsdk-portable/common/cl_entity.h")

# 7. memory: surface cache sized for the small screen (16-bit pixels; 5 screens worth)
def surfcache(t):
    if "XASH_LIBRETRO" in t:
        return t
    old = "\t\tsize = SURFCACHE_SIZE_AT_320X240 * 2;\n\n\t\tpix = vid.width * vid.height * 2;\n\t\tif( pix > 64000 )\n\t\t\tsize += ( pix - 64000 ) * 3;\n"
    assert old in t
    return t.replace(old, "#if XASH_LIBRETRO\n\t\tsize = Q_max( vid.width * vid.height * 2 * 5, 512 * 1024 );\n\t\t(void)pix;\n#else\n" + old + "#endif\n", 1)
patch("ref/soft/r_surf.c", surfcache)

# 8. memory + cache: textures with at most 256 colours (every WAD/BSP/MDL/SPR texture) are kept as 8-bit indices
#    plus a 256-entry palette of the renderer's 16-bit pixels, all four mips (half the memory of 16-bit). The
#    surface-cache builders read them directly (r_pal8[idx]). Users of the 16-bit pixels[0] (models, sprites,
#    2D, water, sky, decals, TriAPI) get it expanded on first use (R_TexPixels).
import re as _re
def local_h(t):
    if "R_TexPixels" in t:
        return t
    old = "\tpixel_t        *alpha_pixels;                           // mip levels\n"
    assert old in t
    t = t.replace(old, old + "\tbyte           *idx[4];                                 // 8-bit mips (palette in pal8), or NULL\n\tpixel_t        *pal8;\n", 1)
    old = "extern viddef_t vid;\n"
    assert old in t
    t = t.replace(old, old + "struct image_s;\npixel_t *R_TexPixels( struct image_s *tex );   // 16-bit mip 0, expanded from the 8-bit copy on first use\n", 1)
    return t
patch("ref/soft/r_local.h", local_h)

def image_c(t):
    if "R_TexPixels" in t:
        return t
    # upload: convert every mip to pixel_t in a temporary buffer, then try to index it
    old = "\t\ttex->pixels[j] = (pixel_t *)Mem_Calloc( r_temppool, width * height * sizeof( pixel_t ));\n"
    assert old in t
    t = t.replace(old, "\t\ttex->pixels[j] = (pixel_t *)Mem_Calloc( r_temppool, width * height * sizeof( pixel_t ));\n", 1)
    old = "\t\tif( mipCount > 1 )\n\t\t\tGL_BuildMipMap( data, width, height, tex->depth, tex->flags );\n"
    assert old in t
    t = t.replace(old, "\t\tR_TexTryIndex( tex, j, width * height );\n" + old, 1)
    helper = r'''
// ---- 8-bit texture storage (R36HD libretro core)
static int r_tex8_off = -1;
static int R_PalFind( const pixel_t *pal, int n, pixel_t p )
{
	for( int i = 0; i < n; i++ ) if( pal[i] == p ) return i;
	return -1;
}
// decode the renderer's pixel (332 major + GBRGBRGB minor) back to 5:6:5
static void R_PixTo565( pixel_t p, int *r, int *g, int *b )
{
	unsigned major = p >> 8, minor = p & 0xFF;
	*r = (( major >> 5 ) & 7 ) << 2 | ((( minor >> 5 ) & 1 ) << 1 ) | (( minor >> 2 ) & 1 );
	*g = (( major >> 2 ) & 7 ) << 3 | ((( minor >> 7 ) & 1 ) << 2 ) | ((( minor >> 4 ) & 1 ) << 1 ) | (( minor >> 1 ) & 1 );
	*b = ( major & 3 ) << 3 | ((( minor >> 6 ) & 1 ) << 2 ) | ((( minor >> 3 ) & 1 ) << 1 ) | ( minor & 1 );
}
static int R_PalNearest( const pixel_t *pal, int n, pixel_t p )
{
	int r, g, b, best = 0, bestd = 0x7fffffff;
	R_PixTo565( p, &r, &g, &b );
	for( int i = 0; i < n; i++ )
	{
		int r2, g2, b2;
		if( pal[i] == TRANSPARENT_COLOR ) continue;
		R_PixTo565( pal[i], &r2, &g2, &b2 );
		int d = ( r - r2 ) * ( r - r2 ) * 4 + ( g - g2 ) * ( g - g2 ) + ( b - b2 ) * ( b - b2 ) * 4;
		if( d < bestd ) { bestd = d; best = i; }
	}
	return best;
}
// called after mip j was converted into tex->pixels[j]
static void R_TexTryIndex( image_t *tex, int j, int n )
{
	if( r_tex8_off < 0 ) r_tex8_off = 0;
	if( r_tex8_off ) return;
	pixel_t *src = tex->pixels[j];
	if( j == 0 )
	{
		// mip 0 decides: at most 256 different pixels
		pixel_t pal[256];
		int np = 0;
		for( int i = 0; i < n; i++ )
		{
			if( np && pal[np - 1] == src[i] ) continue;
			if( R_PalFind( pal, np, src[i] ) >= 0 ) continue;
			if( np == 256 ) return;            // too many colours: stays 16-bit
			pal[np++] = src[i];
		}
		tex->pal8 = (pixel_t *)Mem_Calloc( r_temppool, 256 * sizeof( pixel_t ));
		memcpy( tex->pal8, pal, np * sizeof( pixel_t ));
		for( int i = np; i < 256; i++ ) tex->pal8[i] = pal[0];
	}
	else if( !tex->idx[0] )
		return;
	byte *ix = (byte *)Mem_Malloc( r_temppool, n );
	int last = -1; pixel_t lastp = 0;
	for( int i = 0; i < n; i++ )
	{
		if( last >= 0 && src[i] == lastp ) { ix[i] = last; continue; }
		int k = R_PalFind( tex->pal8, 256, src[i] );
		if( k < 0 ) k = R_PalNearest( tex->pal8, 256, src[i] );   // averaged mip colour
		ix[i] = last = k; lastp = src[i];
	}
	tex->idx[j] = ix;
	Mem_Free( tex->pixels[j] );
	tex->pixels[j] = NULL;
}

pixel_t *R_TexPixels( image_t *tex )
{
	if( !tex->pixels[0] && tex->idx[0] )
	{
		int n = tex->width * tex->height;
		pixel_t *p = (pixel_t *)Mem_Malloc( r_temppool, n * sizeof( pixel_t ));
		for( int i = 0; i < n; i++ ) p[i] = tex->pal8[tex->idx[0][i]];
		tex->pixels[0] = p;
	}
	return tex->pixels[0];
}
'''
    anchor = "/*\n===============\nGL_UploadTexture\n"
    assert anchor in t
    t = t.replace(anchor, helper + anchor, 1)
    # free the 8-bit copies with the texture
    old = "\tif( tex->alpha_pixels )\n\t\tMem_Free( tex->alpha_pixels );\n"
    assert old in t
    t = t.replace(old, old + "\tfor( int k = 0; k < 4; k++ )\n\t\tif( tex->idx[k] )\n\t\t\tMem_Free( tex->idx[k] );\n\tif( tex->pal8 )\n\t\tMem_Free( tex->pal8 );\n", 1)
    # 'texture uploaded' checks look at pixels[0]
    t = t.replace("\tif( !tex->pixels[0] )\n", "\tif( !tex->pixels[0] && !tex->idx[0] )\n", 1)
    # TriAPI / studio bind
    t = t.replace("r_affinetridesc.pskin = image->pixels[0];", "r_affinetridesc.pskin = R_TexPixels( image );")
    return t
patch("ref/soft/r_image.c", image_c)

def other_users(t):
    if "R_TexPixels" in t:
        return t
    t2 = t.replace("pic->pixels[0]", "R_TexPixels( pic )").replace("tex->pixels[0]", "R_TexPixels( tex )")
    t2 = t2.replace("R_GetTexture( pface->texinfo->texture->gl_texturenum )->pixels[0]", "R_TexPixels( R_GetTexture( pface->texinfo->texture->gl_texturenum ))")
    t2 = t2.replace("image->pixels[0]", "R_TexPixels( image )")
    return t2
for f in ("ref/soft/r_draw.c", "ref/soft/r_sprite.c"):
    patch(f, other_users)

def edge_c(t):
    if "R_TexPixels" in t:
        return t
    t = t.replace("return tex->pixels[0][ty * tex->width + tx];", "return R_TexPixels( (image_t *)tex )[ty * tex->width + tx];")
    t = t.replace("R_GetTexture( pface->texinfo->texture->gl_texturenum )->pixels[0]", "R_TexPixels( R_GetTexture( pface->texinfo->texture->gl_texturenum ))")
    assert t.count("R_TexPixels") == 3, t.count("R_TexPixels")
    return t
patch("ref/soft/r_edge.c", edge_c)

def surf_c(t):
    if "r_pal8" in t:
        return t
    # decals and anything else reading mip 0 directly
    t = t.replace("if( !tex->pixels[0] || s1 >= s2", "if( !R_TexPixels( tex ) || s1 >= s2")
    t = t.replace("\t\t\tbuffer = tex->pixels[0];", "\t\t\tbuffer = R_TexPixels( tex );")
    t = t.replace("static pixel_t    *r_source, *r_sourcemax;",
                  "static pixel_t    *r_source, *r_sourcemax;\nstatic const byte *r_source8, *r_sourcemax8;   // 8-bit textures: same offsets as r_source\nstatic const pixel_t *r_pal8;", 1)
    old = "\tr_source = mt->pixels[r_drawsurf.surfmip];\n"
    assert old in t
    t = t.replace(old, "\tr_source8 = mt->idx[r_drawsurf.surfmip];\n\tr_pal8 = mt->pal8;\n\tr_source = r_source8 ? (pixel_t *)r_source8 : mt->pixels[r_drawsurf.surfmip];   // only offsets are taken from it when 8-bit\n", 1)
    old = "\tr_sourcemax = r_source + ( tmax * smax );\n"
    assert old in t
    t = t.replace(old, old + "\tr_sourcemax8 = r_source8 + ( tmax * smax );\n", 1)
    # 8-bit copies of the block drawers
    names = ["World", "Generic", "mip0", "mip1", "mip2", "mip3"]
    copies = []
    for n in names:
        m = _re.search(r"\nvoid R_DrawSurfaceBlock8_%s\( void \)\n\{.*?\n\}\n" % n, t, _re.S)
        assert m, n
        body = m.group(0)
        b = body.replace("R_DrawSurfaceBlock8_%s(" % n, "R_DrawSurfaceBlock8_%s_I8(" % n)
        b = b.replace("pixel_t pix, *psource, *prowdest;", "pixel_t pix, *prowdest; const byte *psource;")
        b = b.replace("psource = pbasesource;", "psource = r_source8 + ( pbasesource - r_source );")
        b = b.replace("pix = psource[b];", "pix = r_pal8[psource[b]];")
        b = b.replace("if( psource >= r_sourcemax )", "if( psource >= r_sourcemax8 )")
        assert "r_pal8[psource[b]]" in b and "r_sourcemax8" in b, n
        copies.append(b)
    anchor = "// ============================================================================\n/*\n================\nR_InitCaches\n"
    assert anchor in t
    t = t.replace(anchor, "// 8-bit source texture versions (generated by tools/patch_hl_sources.py)\n" + "".join(copies) + anchor, 1)
    decl = "void R_DrawSurfaceBlock8_World( void );\n"
    t = t.replace(decl, decl + "".join("void R_DrawSurfaceBlock8_%s_I8( void );\n" % n for n in names) +
                  "static void     (*surfmiptable_i8[4])( void ) = { R_DrawSurfaceBlock8_mip0_I8, R_DrawSurfaceBlock8_mip1_I8, R_DrawSurfaceBlock8_mip2_I8, R_DrawSurfaceBlock8_mip3_I8 };\n", 1)
    old = "\tif( sample_size == 16 )\n\t\tpblockdrawer = surfmiptable[r_drawsurf.surfmip];\n\telse\n\t\tpblockdrawer = R_DrawSurfaceBlock8_Generic;\n"
    assert old in t
    t = t.replace(old, "\tif( sample_size == 16 )\n\t\tpblockdrawer = r_source8 ? surfmiptable_i8[r_drawsurf.surfmip] : surfmiptable[r_drawsurf.surfmip];\n\telse\n\t\tpblockdrawer = r_source8 ? R_DrawSurfaceBlock8_Generic_I8 : R_DrawSurfaceBlock8_Generic;\n", 1)
    old = "\t\t\tR_DrawSurfaceBlock8_World();\n"
    assert old in t
    t = t.replace(old, "\t\t\tif( r_source8 ) R_DrawSurfaceBlock8_World_I8(); else R_DrawSurfaceBlock8_World();\n", 1)
    return t
patch("ref/soft/r_surf.c", surf_c)

# 9. memory: mip levels 1-3 are only read by the surface-cache builder, i.e. for world textures. Everything
#    else (models, sprites, 2D, sky, decals, fonts) gets mip 0 only.
def mips_c(t):
    if "R_TexNeedsMips" in t:
        return t
    old = "\tint mipCount = 4;\n"
    assert old in t
    t = t.replace(old, "\tint mipCount = R_TexNeedsMips( tex ) ? 4 : 1;\n", 1)
    helper = r'''
static qboolean R_TexNeedsMips( const image_t *tex )
{
	const char *n = tex->name;
	if( FBitSet( tex->flags, TF_NOMIPMAP )) return false;
	if( !Q_strnicmp( n, "#maps/", 6 )) return true;                  // world and brush-model textures
	if( n[0] == '#' || n[0] == '*' ) return false;                    // models, sprites, HUD, engine internal
	if( !Q_strnicmp( n, "gfx/", 4 ) || !Q_strnicmp( n, "sprites/", 8 ) || !Q_strnicmp( n, "models/", 7 )
		|| !Q_strnicmp( n, "decals.wad", 10 ) || !Q_strnicmp( n, "fonts.wad", 9 ) || !Q_strnicmp( n, "gfx.wad", 7 )
		|| !Q_strnicmp( n, "cached.wad", 10 ) || Q_stristr( n, ".spr" ) || Q_stristr( n, ".mdl" ) || Q_stristr( n, ".lmp" )
		|| Q_stristr( n, ".tga" ) || Q_stristr( n, ".bmp" ))
		return false;
	return true;
}
'''
    anchor = "/*\n===============\nGL_UploadTexture\n"
    t = t.replace(anchor, helper + anchor, 1)
    return t
patch("ref/soft/r_image.c", mips_c)

# 10. speed: palette lookups at texture load through a 64K map instead of a linear search per pixel (was 13% of
#     all instructions: level loads stalled)
def texidx_fast(t):
    if "r_palmap" in t:
        return t
    old = "static int R_PalFind( const pixel_t *pal, int n, pixel_t p )\n{\n\tfor( int i = 0; i < n; i++ ) if( pal[i] == p ) return i;\n\treturn -1;\n}\n"
    assert old in t
    t = t.replace(old, old + "static unsigned short *r_palmap;   // pixel -> index+1 for the texture being uploaded (128 KB)\n", 1)
    # mip 0: build palette with the map
    old = "\t\tfor( int i = 0; i < n; i++ )\n\t\t{\n\t\t\tif( np && pal[np - 1] == src[i] ) continue;\n\t\t\tif( R_PalFind( pal, np, src[i] ) >= 0 ) continue;\n\t\t\tif( np == 256 ) return;            // too many colours: stays 16-bit\n\t\t\tpal[np++] = src[i];\n\t\t}\n"
    assert old in t
    t = t.replace(old, "\t\tif( !r_palmap ) r_palmap = (unsigned short *)malloc( 65536 * 2 );\n\t\tmemset( r_palmap, 0, 65536 * 2 );\n"
        "\t\tfor( int i = 0; i < n; i++ )\n\t\t{\n\t\t\tif( r_palmap[src[i]] ) continue;\n\t\t\tif( np == 256 ) { free( r_palmap ); r_palmap = NULL; return; }   // too many colours: stays 16-bit\n"
        "\t\t\tpal[np] = src[i];\n\t\t\tr_palmap[src[i]] = ++np;\n\t\t}\n", 1)
    # index lookup
    old = "\t\tint k = R_PalFind( tex->pal8, 256, src[i] );\n"
    assert old in t
    t = t.replace(old, "\t\tint k = r_palmap && r_palmap[src[i]] ? r_palmap[src[i]] - 1 : -1;\n\t\tif( k < 0 ) k = R_PalFind( tex->pal8, 256, src[i] );\n", 1)
    return t
patch("ref/soft/r_image.c", texidx_fast)

# 11. memory: sounds load on first play instead of at level start, and the cache is kept under 1024 KB
#     by freeing the least recently played sounds that no channel uses
def sndcache(t):
    if "lr_snd_bytes" in t:
        return t
    old = "\t// see if still in memory\n\tif( sfx->cache )\n\t\treturn sfx->cache;\n"
    assert old in t
    t = t.replace(old, "\t// see if still in memory\n\tif( sfx->cache )\n\t{\n#if XASH_LIBRETRO\n\t\tlr_snd_lastuse[sfx - s_knownSfx] = ++lr_snd_clock;\n#endif\n\t\treturn sfx->cache;\n\t}\n#if XASH_LIBRETRO\n\tLR_SndMakeRoom( sfx );\n#endif\n", 1)
    old = "\tsfx->cache = sc;\n\n\treturn sfx->cache;\n}\n"
    assert old in t
    t = t.replace(old, "\tsfx->cache = sc;\n#if XASH_LIBRETRO\n\tlr_snd_bytes += sc->size;\n\tlr_snd_lastuse[sfx - s_knownSfx] = ++lr_snd_clock;\n#endif\n\n\treturn sfx->cache;\n}\n", 1)
    helper = r'''
#if XASH_LIBRETRO
static size_t lr_snd_bytes;
static uint lr_snd_clock, lr_snd_lastuse[MAX_SFX];
static qboolean LR_SndInUse( const sfx_t *sfx )
{
	for( int i = 0; i < snd.total_channels; i++ )
	{
		const channel_t *ch = &snd.channels[i];
		if( ch->sfx == sfx || ( sfx->cache && ch->data == sfx->cache )) return true;
		if( ch->words ) for( const voxword_t *w = ch->words; w->sfx; w++ ) if( w->sfx == sfx ) return true;
	}
	return false;
}
static void LR_SndMakeRoom( const sfx_t *want )
{
	static size_t budget;
	if( !budget ) budget = (size_t)6144 * 1024;
	while( lr_snd_bytes > budget )
	{
		sfx_t *victim = NULL;
		uint oldest = 0xffffffff;
		for( int i = 0; i < s_numSfx; i++ )
		{
			sfx_t *s = &s_knownSfx[i];
			if( !s->cache || s == want || !Q_stricmp( s->name, "*default" )) continue;
			if( lr_snd_lastuse[i] < oldest && !LR_SndInUse( s )) { oldest = lr_snd_lastuse[i]; victim = s; }
		}
		if( !victim ) break;
		lr_snd_bytes -= victim->cache->size < lr_snd_bytes ? victim->cache->size : lr_snd_bytes;
		FS_FreeSound( victim->cache );
		victim->cache = NULL;
	}
}
#endif
'''
    anchor = "/*\n=================\nS_LoadSound\n"
    assert anchor in t
    t = t.replace(anchor, helper + anchor, 1)
    # S_FreeSound keeps the count right
    old = "\tif( sfx->cache )\n\t\tFS_FreeSound( sfx->cache );\n"
    assert old in t
    t = t.replace(old, "#if XASH_LIBRETRO\n\tif( sfx->cache ) lr_snd_bytes -= sfx->cache->size < lr_snd_bytes ? sfx->cache->size : lr_snd_bytes;\n#endif\n" + old, 1)
    # no loading of every precached sound at level start
    old = "\t// load everything in\n\tfor( i = 0, sfx = s_knownSfx; i < s_numSfx; i++, sfx++ )\n\t{\n\t\tif( !sfx->name[0] )\n\t\t\tcontinue;\n\t\tS_LoadSound( sfx );\n\t}\n"
    assert old in t
    t = t.replace(old, "#if !XASH_LIBRETRO\n" + old + "#endif\n", 1)
    t = t.replace("\tif( !s_registering ) S_LoadSound( sfx );\n", "#if !XASH_LIBRETRO\n\tif( !s_registering ) S_LoadSound( sfx );\n#endif\n", 1)
    return t
patch("engine/client/sound/s_load.c", sndcache)

# 12. memory: directory cache entries keep 64-byte names instead of 256 (about 400 KB less with valve/ scanned)
def dirnames(t):
    if "XASH_LIBRETRO" in t:
        return t
    old = "typedef struct dir_s\n{\n\tstring name;\n"
    assert old in t
    return t.replace(old, "typedef struct dir_s\n{\n#if XASH_LIBRETRO\n\tchar name[64];\n#else\n\tstring name;\n#endif\n", 1)
patch("filesystem/dir.c", dirnames)

# 13. speed: surface cache back to the original size (512 KB rebuilt surfaces every frame: 25% of all instructions)
def surfcache2(t):
    return t.replace("size = Q_max( vid.width * vid.height * 2 * 5, 512 * 1024 );", "size = Q_max( vid.width * vid.height * 2 * 8, 1280 * 1024 );")
patch("ref/soft/r_surf.c", surfcache2)

# 14. speed: remember the nearest palette entry of averaged mip colours (the search was most of a level load)
def nearest_cache(t):
    old = "\t\tif( k < 0 ) k = R_PalFind( tex->pal8, 256, src[i] );\n"
    if old not in t:
        return t
    return t.replace(old, "\t\tif( k < 0 ) { k = R_PalNearest( tex->pal8, 256, src[i] ); if( r_palmap ) r_palmap[src[i]] = k + 1; }\n", 1)
patch("ref/soft/r_image.c", nearest_cache)

# 15. crash on MIPS: CRestore::ReadField reads ints/floats from unaligned places in the save buffer (level changes,
#     saves): SIGBUS. Read them with memcpy, like the ARM VFP path already does for floats and vectors
def util_unaligned(t):
    if "LR_RD_INT" in t:
        return t
    a = t.index("int CRestore::ReadField(")
    b = t.index("Bad field type", a)
    body = t[a:b]
    body = body.replace("#if __VFP_FP__", "#if __VFP_FP__ || __mips__").replace("#if  __VFP_FP__", "#if __VFP_FP__ || __mips__")
    body = body.replace("*( int *)pInputData", "LR_RD_INT( pInputData )").replace("*(int *)pInputData", "LR_RD_INT( pInputData )")
    body = body.replace("*(short *)pInputData", "LR_RD_SHORT( pInputData )").replace("*(size_t *)pInputData", "LR_RD_SIZE( pInputData )")
    assert "LR_RD_INT" in body and "LR_RD_SHORT" in body
    helpers = ("static inline int LR_RD_INT( const void *p ) { int v; memcpy( &v, p, sizeof( v )); return v; }\n"
               "static inline short LR_RD_SHORT( const void *p ) { short v; memcpy( &v, p, sizeof( v )); return v; }\n"
               "static inline size_t LR_RD_SIZE( const void *p ) { size_t v; memcpy( &v, p, sizeof( v )); return v; }\n\n")
    return t[:a] + helpers + body + t[b:]
p = pathlib.Path("third_party/hlsdk-portable/dlls/util.cpp")
raw = p.read_bytes(); crlf = b"\r\n" in raw
t = raw.decode("latin-1").replace("\r\n", "\n")
n = util_unaligned(t)
if n != t:
    if crlf: n = n.replace("\n", "\r\n")
    p.write_bytes(n.encode("latin-1")); print("patched   hlsdk-portable/dlls/util.cpp")
else:
    print("unchanged hlsdk-portable/dlls/util.cpp")

# 16. crash on MIPS: R_RenderFace trusts a stale cachededgeoffset (left from the previous map) and reads
#     ->owner through it; an offset that is not a whole edge_t is unaligned (SIGBUS). Only offsets that are
#     multiples of sizeof( edge_t ) can be cached edges.
def rast_align(t):
    if "% sizeof( edge_t )" in t:
        return t
    old = "\t\t\t\t\tif((((uintptr_t)edge_p - (uintptr_t)r_edges )\n\t\t\t\t\t    > r_pedge->cachededgeoffset )\n"
    n = t.count(old)
    assert n >= 1, n
    return t.replace(old, "\t\t\t\t\tif((((uintptr_t)edge_p - (uintptr_t)r_edges )\n\t\t\t\t\t    > r_pedge->cachededgeoffset ) && !( r_pedge->cachededgeoffset % sizeof( edge_t ))\n")
patch("ref/soft/r_rast.c", rast_align)

# 17. speed: blit two pixels per 32-bit load/store, next-row prefetch
def blit2(t):
    if "LR_BLIT2" in t:
        return t
    old = """			unsigned short *pbuf = buffer;
			for( int v = 0; v < vid.height; v++ )
			{
				uint start = vid.rowbytes * v;
				uint dstart = swblit.stride * v;

				for( int u = 0; u < vid.width; u++ )
				{
					unsigned int s = vid.screen[vid.buffer[start + u]];
					pbuf[dstart + u] = s;
				}
			}
"""
    assert old in t
    new = """			unsigned short *pbuf = buffer;
			// LR_BLIT2: two pixels per 32-bit load and store (width is even), next row prefetched
			for( int v = 0; v < vid.height; v++ )
			{
				const uint32_t *src = (const uint32_t *)( vid.buffer + vid.rowbytes * v );
				uint32_t *dst = (uint32_t *)( pbuf + swblit.stride * v );
				const pixel_t *scr = vid.screen;
				int n = vid.width >> 1;
				__builtin_prefetch( src + vid.rowbytes / 2 );
				for( int u = 0; u < n; u++ )
				{
					uint32_t p = src[u];
					dst[u] = (uint32_t)scr[p & 0xffff] | ((uint32_t)scr[p >> 16] << 16);
				}
			}
"""
    return t.replace(old, new, 1)
patch("ref/soft/r_glblit.c", blit2)

# 18. speed: texture coordinates without fmodf for the usual 0..10 range (studio models call this per vertex)
def texcoord(t):
    if "LR_FASTUV" in t:
        return t
    old = "\tdouble u1 = 0, v1 = 0;\n\tu = fmodf( u, 10 );\n\tv = fmodf( v, 10 );\n"
    assert old in t
    return t.replace(old, "\tdouble u1 = 0, v1 = 0; // LR_FASTUV\n\tif( !( u >= 0.0f && u < 10.0f )) u = fmodf( u, 10 );\n\tif( !( v >= 0.0f && v < 10.0f )) v = fmodf( v, 10 );\n", 1)
patch("ref/soft/r_triapi.c", texcoord)

# 19. speed: studio meshes project each vertex once per mesh instead of once per strip/fan use
def tri_cache(t):
    if "TriVertexIdx" in t:
        return t
    helper = """
// R36HD: projected-vertex cache for studio meshes (index -> finalvert), valid for one mesh
#define LR_VCACHE 2048
static finalvert_t lr_vcache[LR_VCACHE];
static unsigned lr_vstamp[LR_VCACHE], lr_vframe = 1;
void TriVertexCacheReset( void ) { lr_vframe++; }
void TriVertexIdx( int idx, const float *v )
{
	if( vid.is2d || idx < 0 || idx >= LR_VCACHE || ( mode != TRI_TRIANGLE_STRIP && mode != TRI_TRIANGLE_FAN ))
	{
		TriVertex3f( v[0], v[1], v[2] );
		return;
	}
	finalvert_t *c = &lr_vcache[idx];
	if( lr_vstamp[idx] != lr_vframe )
	{
		R_SetupFinalVert( c, v[0], v[1], v[2], 0, 0, 0 );
		lr_vstamp[idx] = lr_vframe;
	}
	finalvert_t *dst = mode == TRI_TRIANGLE_FAN ? &triv[vertcount < 2 ? vertcount : 2] : &triv[n];
	*dst = *c;
	dst->l = light << 8;
	dst->s = s << 16;
	dst->t = t << 16;
	if( mode == TRI_TRIANGLE_FAN )
	{
		vertcount++;
		if( vertcount >= 3 )
		{
			R_RenderTriangle( &triv[0], &triv[1], &triv[2] );
			triv[1] = triv[2];
			vertcount = 2;
		}
	}
	else
	{
		n++;
		vertcount++;
		if( n == 3 ) n = 0;
		if( vertcount >= 3 )
		{
			if( vertcount & 1 ) R_RenderTriangle( &triv[0], &triv[1], &triv[2] );
			else R_RenderTriangle( &triv[2], &triv[1], &triv[0] );
		}
	}
}
"""
    anchor = "/*\n=============\nTriVertex3fv\n"
    assert anchor in t
    return t.replace(anchor, helper + anchor, 1)
patch("ref/soft/r_triapi.c", tri_cache)

def studio_cache(t):
    if "TriVertexIdx" in t:
        return t
    old = """static void R_StudioDrawNormalMesh( short *ptricmds, vec3_t *pstudionorms, float s, float t )
{
	int   i;
"""
    assert old in t
    t = t.replace(old, "void TriVertexIdx( int idx, const float *v );\nvoid TriVertexCacheReset( void );\n" + old + "\tTriVertexCacheReset();\n", 1)
    a = t.index("static void R_StudioDrawNormalMesh(")
    b = t.index("\n}\n", a)
    body = t[a:b]
    body2 = body.replace("TriVertex3fv( g_studio.verts[ptricmds[0]] );", "TriVertexIdx( ptricmds[0], g_studio.verts[ptricmds[0]] );")
    assert body2 != body
    return t[:a] + body2 + t[b:]
patch("ref/soft/r_studio.c", studio_cache)

# 20. memory: the surface cache must not grow to 4.7 MB when menus/loading switch to 640x480
def surfcache3(t):
    return t.replace("size = Q_max( vid.width * vid.height * 2 * 8, 1280 * 1024 );",
                     "size = Q_min( Q_max( vid.width * vid.height * 2 * 8, 1280 * 1024 ), 1920 * 1024 );")
# 22. with the 48 MB pool the caches may be larger: surface cache cap 4 MB (fewer rebuilt surfaces), sounds kept up to 6 MB
def surfcache4(t):
    return t.replace("1280 * 1024 ), 1920 * 1024 );", "3072 * 1024 ), 4096 * 1024 );")
patch("ref/soft/r_surf.c", surfcache3)
patch("ref/soft/r_surf.c", surfcache4)

# 21. speed: texture coordinate wrap in float with floorf instead of double loops
def texcoord2(t):
    if "LR_FASTUV2" in t:
        return t
    a = t.index("void GAME_EXPORT TriTexCoord2f( float u, float v )")
    b = t.index("\n}\n", a) + 3
    new = """void GAME_EXPORT TriTexCoord2f( float u, float v )
{
	// LR_FASTUV2: same result as the original fmod/loop/bound code for finite input
	if( !( u > -1000.0f && u < 1000.0f )) u = 0.0f;
	if( !( v > -1000.0f && v < 1000.0f )) v = 0.0f;
	u -= floorf( u ); v -= floorf( v );
	if( u < 0.01f ) u = 0.01f; else if( u > 0.99f ) u = 0.99f;
	if( v < 0.01f ) v = 0.01f; else if( v > 0.99f ) v = 0.99f;
	s = r_affinetridesc.skinwidth * u;
	t = r_affinetridesc.skinheight * v;
}
"""
    return t[:a] + new + t[b:]
patch("ref/soft/r_triapi.c", texcoord2)

# 22. speed: blit through two 256-entry tables (1 KB, stays in L1) instead of the 128 KB vid.screen table;
#     the full table is screen[(i<<8)|j] = major(i) | minor(j), so the result is identical
def blit_split(t):
    if "lr_scr_hi" in t:
        return t
    old = "\t\t\t\tconst pixel_t *scr = vid.screen;\n"
    assert old in t
    t = t.replace(old, """				static uint32_t lr_scr_hi[256], lr_scr_lo[256], lr_scr_sig; static const int lr_split = 1;
				if( lr_scr_sig != (uint32_t)vid.screen[0xffff] + 1 )
				{
					for( int k = 0; k < 256; k++ ) { lr_scr_hi[k] = vid.screen[k << 8]; lr_scr_lo[k] = vid.screen[k]; }
					lr_scr_sig = (uint32_t)vid.screen[0xffff] + 1;
				}
""", 1)
    old = "\t\t\t\t\tdst[u] = (uint32_t)scr[p & 0xffff] | ((uint32_t)scr[p >> 16] << 16);\n"
    assert old in t
    t = t.replace(old, "\t\t\t\t\tdst[u] = lr_split ? ( lr_scr_hi[( p >> 8 ) & 0xff] | lr_scr_lo[p & 0xff] ) | (( lr_scr_hi[p >> 24] | lr_scr_lo[( p >> 16 ) & 0xff] ) << 16 ) : (uint32_t)vid.screen[p & 0xffff] | ((uint32_t)vid.screen[p >> 16] << 16);\n", 1)
    return t
patch("ref/soft/r_glblit.c", blit_split)

# 23. speed: world spans step perspective every 16 pixels instead of 8 (half the divides; Quake's own option)
def span16(t):
    if "LR_SPAN16" in t:
        return t
    a = t.index("void D_DrawSpans16( espan_t *pspan )")
    b = t.index("\n}\n", a)
    body = t[a:b]
    body = body.replace("sdivz8stepu = d_sdivzstepu * 8;", "sdivz8stepu = d_sdivzstepu * 16; // LR_SPAN16")
    body = body.replace("tdivz8stepu = d_tdivzstepu * 8;", "tdivz8stepu = d_tdivzstepu * 16;")
    body = body.replace("zi8stepu = d_zistepu * 8;", "zi8stepu = d_zistepu * 16;")
    body = body.replace("if( count >= 8 )\n\t\t\t\tspancount = 8;", "if( count >= 16 )\n\t\t\t\tspancount = 16;")
    body = body.replace("sstep = ( snext - s ) >> 3;", "sstep = ( snext - s ) >> 4;")
    body = body.replace("tstep = ( tnext - t ) >> 3;", "tstep = ( tnext - t ) >> 4;")
    body = body.replace("*pdest++ = *( pbase + ( s >> 16 ) + ( t >> 16 ) * cachewidth );",
                        "*pdest++ = pbase[( s >> 16 ) + ( t >> 16 ) * cachewidth];")
    assert body.count("16;") >= 4 and ">> 4;" in body
    return t[:a] + body + t[b:]
patch("ref/soft/r_scan.c", span16)

# 24. speed: studio vertex colour per normal per mesh (no local lights: it depends only on the normal); the
#     cache is built but left off (see cacheable below)
def tri_color_cache(t):
    if "TriColorIdx" in t:
        return t
    helper = """
// R36HD: per-normal colour cache for studio meshes, same lifetime as the vertex cache
static unsigned lr_cstamp[LR_VCACHE];
static uint lr_clight[LR_VCACHE];
static pixel_t lr_ccolor[LR_VCACHE];
static byte lr_calpha[LR_VCACHE];
qboolean TriColorIdxCached( int idx )
{
	if( idx < 0 || idx >= LR_VCACHE || lr_cstamp[idx] != lr_vframe ) return false;
	light = lr_clight[idx]; vid.color = lr_ccolor[idx]; vid.alpha = lr_calpha[idx];
	return true;
}
void TriColorIdxStore( int idx )
{
	if( idx < 0 || idx >= LR_VCACHE ) return;
	lr_cstamp[idx] = lr_vframe; lr_clight[idx] = light; lr_ccolor[idx] = vid.color; lr_calpha[idx] = vid.alpha;
}
"""
    anchor = "void TriVertexIdx( int idx, const float *v )\n"
    assert anchor in t
    return t.replace(anchor, helper + anchor, 1)
patch("ref/soft/r_triapi.c", tri_color_cache)

def studio_color_cache(t):
    if "TriColorIdxCached" in t:
        return t
    old = """static void R_StudioSetColorBegin( short *ptricmds, vec3_t *pstudionorms )
{
	float  *lv = (float *)g_studio.lightvalues[ptricmds[1]];
	rgba_t color;
"""
    assert old in t
    return t.replace(old, """qboolean TriColorIdxCached( int idx );
void TriColorIdxStore( int idx );
static void R_StudioSetColorBegin( short *ptricmds, vec3_t *pstudionorms )
{
	float  *lv = (float *)g_studio.lightvalues[ptricmds[1]];
	rgba_t color;
	const qboolean cacheable = false; // per-normal cache turned off: no gain
	if( cacheable && TriColorIdxCached( ptricmds[1] )) return;
	color[3] = tr.blend * 255;
	R_LightLambert( g_studio.lightpos[ptricmds[0]], pstudionorms[ptricmds[1]], lv, color );
	TriColor4ub( color[0], color[1], color[2], color[3] );
	if( cacheable ) TriColorIdxStore( ptricmds[1] );
	return;
""", 1)
patch("ref/soft/r_studio.c", studio_color_cache)

# 24b. the colour cache is only valid inside R_StudioDrawNormalMesh (other mesh paths do not reset it)
def tri_color_scope(t):
    if "lr_ccache_on" in t:
        return t
    t = t.replace("void TriVertexCacheReset( void ) { lr_vframe++; }",
                  "static int lr_ccache_on;\nvoid TriVertexCacheReset( void ) { lr_vframe++; lr_ccache_on = 1; }\nvoid TriVertexCacheEnd( void ) { lr_ccache_on = 0; }", 1)
    t = t.replace("\tif( idx < 0 || idx >= LR_VCACHE || lr_cstamp[idx] != lr_vframe ) return false;",
                  "\tif( !lr_ccache_on || idx < 0 || idx >= LR_VCACHE || lr_cstamp[idx] != lr_vframe ) return false;", 1)
    t = t.replace("\tif( idx < 0 || idx >= LR_VCACHE ) return;\n\tlr_cstamp[idx] = lr_vframe;",
                  "\tif( !lr_ccache_on || idx < 0 || idx >= LR_VCACHE ) return;\n\tlr_cstamp[idx] = lr_vframe;", 1)
    assert t.count("lr_ccache_on") == 5, t.count("lr_ccache_on")
    return t
patch("ref/soft/r_triapi.c", tri_color_scope)

def studio_scope(t):
    if "TriVertexCacheEnd" in t:
        return t
    t = t.replace("void TriVertexCacheReset( void );\n", "void TriVertexCacheReset( void );\nvoid TriVertexCacheEnd( void );\n", 1)
    a = t.index("static void R_StudioDrawNormalMesh(")
    b = t.index("\n}\n", a)
    return t[:a] + t[a:b] + "\n\tTriVertexCacheEnd();" + t[b:]
patch("ref/soft/r_studio.c", studio_scope)

# 25. speed: TriColor4ub straight from bytes (it went through floats twice per studio vertex)
def tricolor_int(t):
    if "LR_TRICOLOR_INT" in t:
        return t
    old = """void TriColor4ub( byte r, byte g, byte b, byte a )
{
	ds.triRGBA[0] = r * ( 1.0f / 255.0f );
	ds.triRGBA[1] = g * ( 1.0f / 255.0f );
	ds.triRGBA[2] = b * ( 1.0f / 255.0f );
	ds.triRGBA[3] = a * ( 1.0f / 255.0f );

	_TriColor4f( ds.triRGBA[0], ds.triRGBA[1], ds.triRGBA[2], 1.0f );
}"""
    assert old in t
    new = """void TriColor4ub( byte r, byte g, byte b, byte a )
{
	// LR_TRICOLOR_INT: same as _TriColor4f( r/255, g/255, b/255, 1 ) in integer arithmetic
	static const float k = 1.0f / 255.0f;
	ds.triRGBA[0] = r * k; ds.triRGBA[1] = g * k; ds.triRGBA[2] = b * k; ds.triRGBA[3] = a * k;
	vid.alpha = 7;
	light = ( (uint)r + g + b ) * 31 / 765;
	if( light > 31 ) light = 31;
	if( r == 255 && g == 255 && b == 255 ) { vid.color = COLOR_WHITE; return; }
	unsigned short r5 = r * 31 / 255, g6 = g * 63 / 255, b5 = b * 31 / 255;
	unsigned int major = ((( r5 >> 2 ) & MASK( 3 )) << 5 ) | (((( g6 >> 3 ) & MASK( 3 )) << 2 )) | ((( b5 >> 3 ) & MASK( 2 )));
	unsigned int minor = MOVE_BIT( r5, 1, 5 ) | MOVE_BIT( r5, 0, 2 ) | MOVE_BIT( g6, 2, 7 ) | MOVE_BIT( g6, 1, 4 ) | MOVE_BIT( g6, 0, 1 ) | MOVE_BIT( b5, 2, 6 ) | MOVE_BIT( b5, 1, 3 ) | MOVE_BIT( b5, 0, 0 );
	vid.color = major << 8 | ( minor & 0xFF );
}"""
    return t.replace(old, new, 1)
patch("ref/soft/r_triapi.c", tricolor_int)

# 26. speed: TriColor4ub skips the work when called with the same colour as last time
def tricolor_memo(t):
    if "lr_last_rgba" in t:
        return t
    old = "\t// LR_TRICOLOR_INT: same as _TriColor4f( r/255, g/255, b/255, 1 ) in integer arithmetic\n"
    assert old in t
    return t.replace(old, old + "\tstatic uint32_t lr_last_rgba = 0xffffffff; static uint lr_last_light; static pixel_t lr_last_color;\n"
        "\tuint32_t key = (uint32_t)r | (uint32_t)g << 8 | (uint32_t)b << 16 | (uint32_t)a << 24;\n"
        "\tif( key == lr_last_rgba ) { ds.triRGBA[3] = a * ( 1.0f / 255.0f ); vid.alpha = 7; light = lr_last_light; vid.color = lr_last_color; return; }\n", 1).replace(
        "\tvid.color = major << 8 | ( minor & 0xFF );\n}", "\tvid.color = major << 8 | ( minor & 0xFF );\n\tlr_last_rgba = key; lr_last_light = light; lr_last_color = vid.color;\n}", 1).replace(
        "\tif( r == 255 && g == 255 && b == 255 ) { vid.color = COLOR_WHITE; return; }",
        "\tif( r == 255 && g == 255 && b == 255 ) { vid.color = COLOR_WHITE; lr_last_rgba = key; lr_last_light = light; lr_last_color = vid.color; return; }", 1)
patch("ref/soft/r_triapi.c", tricolor_memo)

# 27. fix 26: its "store" line landed in _TriColor4f (first match) instead of TriColor4ub
def tricolor_memo_fix(t):
    bad = "\tvid.color = major << 8 | ( minor & 0xFF );\n\tlr_last_rgba = key; lr_last_light = light; lr_last_color = vid.color;\n}"
    good = "\tvid.color = major << 8 | ( minor & 0xFF );\n}"
    a = t.find("void TriColor4ub( byte r")
    b = t.find("\n}\n", a)
    head, body, tail = t[:a], t[a:b + 3], t[b + 3:]
    head = head.replace(bad, good)
    if "lr_last_rgba = key; lr_last_light = light; lr_last_color = vid.color;\n}" not in body:
        body = body.replace("\tvid.color = major << 8 | ( minor & 0xFF );\n}", bad, 1)
    return head + body + tail
patch("ref/soft/r_triapi.c", tricolor_memo_fix)

# 29. speed: direct studio mesh path. When only the light value reaches the rasterizer (R_PolysetFillSpans8,
# no local lights) the per-vertex TriColor4ub/TriTexCoord2f/TriVertexIdx calls are replaced by one loop with
# the light precomputed per normal. Output is the same as the TriAPI path.
STUDIO_FAST = r'''
// R36HD LR_STUDIO_FAST: one studio mesh straight to R_RenderTriangle (see r_studio.c R_StudioDrawNormalMesh)
void TriStudioMeshFast( short *ptricmds, const vec3_t *verts, const byte *nlight, float sc, float tc )
{
	const int sw = r_affinetridesc.skinwidth, sh = r_affinetridesc.skinheight;
	int i;
	lr_vframe++;
	while(( i = *( ptricmds++ )))
	{
		const int fan = i < 0;
		int cnt = 0, slot = 0;
		if( fan ) i = -i;
		for( ; i > 0; i--, ptricmds += 4 )
		{
			const int idx = ptricmds[0];
			float u = ptricmds[2] * sc, v = ptricmds[3] * tc;
			short ss, tt;
			finalvert_t *dst;
			if( !( u > -1000.0f && u < 1000.0f )) u = 0.0f;
			if( !( v > -1000.0f && v < 1000.0f )) v = 0.0f;
			u -= floorf( u ); v -= floorf( v );
			if( u < 0.01f ) u = 0.01f; else if( u > 0.99f ) u = 0.99f;
			if( v < 0.01f ) v = 0.01f; else if( v > 0.99f ) v = 0.99f;
			ss = sw * u; tt = sh * v;
			dst = fan ? &triv[cnt < 2 ? cnt : 2] : &triv[slot];
			if( idx >= 0 && idx < LR_VCACHE )
			{
				finalvert_t *c = &lr_vcache[idx];
				if( lr_vstamp[idx] != lr_vframe )
				{
					R_SetupFinalVert( c, verts[idx][0], verts[idx][1], verts[idx][2], 0, 0, 0 );
					lr_vstamp[idx] = lr_vframe;
				}
				*dst = *c;
			}
			else R_SetupFinalVert( dst, verts[idx][0], verts[idx][1], verts[idx][2], 0, 0, 0 );
			dst->l = nlight[ptricmds[1]] << 8;
			dst->s = ss << 16;
			dst->t = tt << 16;
			cnt++;
			if( fan )
			{
				if( cnt >= 3 )
				{
					R_RenderTriangle( &triv[0], &triv[1], &triv[2] );
					triv[1] = triv[2];
					cnt = 2;
				}
			}
			else
			{
				if( ++slot == 3 ) slot = 0;
				if( cnt >= 3 )
				{
					if( cnt & 1 ) R_RenderTriangle( &triv[0], &triv[1], &triv[2] );
					else R_RenderTriangle( &triv[2], &triv[1], &triv[0] );
				}
			}
		}
	}
	vid.alpha = 7;
}
'''
def studio_fast_tri(t):
    if "LR_STUDIO_FAST" in t:
        return t
    anchor = "/*\n=============\nTriVertex3fv\n"
    assert anchor in t
    return t.replace(anchor, STUDIO_FAST + anchor, 1)
patch("ref/soft/r_triapi.c", studio_fast_tri)

def studio_fast_mesh(t):
    if "LR_STUDIO_FAST" in t:
        return t
    # per-normal light byte, same arithmetic as R_LightLambert (no local lights) + TriColor4ub
    old = "\t\t\t\tVectorScale( g_studio.lightcolor, lv_tmp, g_studio.lightvalues[k] );\n"
    assert old in t
    t = t.replace(old, old + "\t\t\t\tLR_NormLight( k );\n", 1)
    old = "\t\t\t\tVectorSet( g_studio.lightvalues[k], tr.blend, tr.blend, tr.blend );\n"
    assert old in t
    t = t.replace(old, old + "\t\t\t\tLR_NormLight( k );\n", 1)
    old = "static void R_StudioDrawNormalMesh( short *ptricmds, vec3_t *pstudionorms, float s, float t )\n{\n\tint   i;\n"
    assert old in t
    t = t.replace(old, old + "\tif( !g_studio.numlocallights && d_pdrawspans == R_PolysetFillSpans8 && !vid.is2d )\n"
        "\t{\t// LR_STUDIO_FAST\n\t\tTriStudioMeshFast( ptricmds, (const vec3_t *)g_studio.verts, lr_nlight, s, t );\n\t\treturn;\n\t}\n", 1)
    old = "void TriVertexIdx( int idx, const float *v );\n"
    assert old in t
    t = t.replace(old, old + "void TriStudioMeshFast( short *ptricmds, const vec3_t *verts, const byte *nlight, float sc, float tc );\n", 1)
    # helper, defined after g_studio
    old = "qboolean TriColorIdxCached( int idx );\n"
    assert old in t
    t = t.replace(old, "static byte lr_nlight[MAXSTUDIOVERTS];\n"
        "static inline void LR_NormLight( int k )\n{\n"
        "\tconst float *lv = g_studio.lightvalues[k];\n"
        "\tbyte r = lv[0] * 255.0f, g = lv[1] * 255.0f, b = lv[2] * 255.0f;\n"
        "\tuint l = ((uint)r + g + b ) * 31 / 765;\n"
        "\tlr_nlight[k] = l > 31 ? 31 : l;\n}\n" + old, 1)
    # vertex loops: R_LightStrength does nothing useful without local lights
    old = "\t\t\tR_LightStrength( pvertbone[i], pstudioverts[i], g_studio.lightpos[i] );\n"
    assert t.count(old) == 2
    t = t.replace(old, "\t\t\tif( g_studio.numlocallights ) R_LightStrength( pvertbone[i], pstudioverts[i], g_studio.lightpos[i] );\n")
    return t
patch("ref/soft/r_studio.c", studio_fast_mesh)

# 30. speed: CL_ParseClientData marked every missed sequence number one by one (36K loop passes per call in
# the first level); the frame window is CL_UPDATE_BACKUP slots, so only the last that many can change.
def dropped_frames(t):
    old = "\t\tfor( j = cl.last_incoming_sequence + 1; j < i; j++ )\n"
    new = "\t\tfor( j = Q_max( cl.last_incoming_sequence + 1, i - CL_UPDATE_BACKUP ); j < i; j++ ) // LR_DROPCAP\n"
    if "LR_DROPCAP" in t:
        return t
    assert old in t
    return t.replace(old, new, 1)
patch("engine/client/parse/cl_parse.c", dropped_frames)

# 31. memory: model skins are drawn from their 8-bit indices + palette (R_PolysetFillSpans8_I8). Before, the
# first draw of a skin expanded it to 16 bits and kept both copies. r_affinetridesc.pskin then points at the
# index bytes but is still stepped as pixel_t*: only the I8 fill turns the offset into a byte address.
FILL_I8 = r'''
// R36HD LR_SKIN_I8: R_PolysetFillSpans8 for an 8-bit skin (r_skinpal8 = its palette)
pixel_t *r_skinpal8;
void R_PolysetFillSpans8_I8( spanpackage_t *pspanpackage )
{
	const byte *base8 = (const byte *)r_affinetridesc.pskin;
	const pixel_t *base16 = (const pixel_t *)r_affinetridesc.pskin;
	const pixel_t *pal = r_skinpal8;
	const int skinwidth = r_affinetridesc.skinwidth;
	int lcount;

	do
	{
		lcount = d_aspancount - pspanpackage->count;

		errorterm += erroradjustup;
		if( errorterm >= 0 )
		{
			d_aspancount += d_countextrastep;
			errorterm -= erroradjustdown;
		}
		else
		{
			d_aspancount += ubasestep;
		}

		if( lcount )
		{
			pixel_t *lpdest = pspanpackage->pdest;
			pixel_t *lptex = pspanpackage->ptex;
			short   *lpz = pspanpackage->pz;
			int     lsfrac = pspanpackage->sfrac;
			int     ltfrac = pspanpackage->tfrac;
			int     llight = pspanpackage->light;
			int     lzi = pspanpackage->zi;
			const byte *lp8;
			pspanpackage++;
#if BOUNDCHECK_MODE == 0
			if( !R_PolysetCheckBounds( lptex, lsfrac, ltfrac, lcount ))
				continue;
#endif
			lp8 = base8 + ( lptex - base16 );
			do
			{
				if(( lzi >> 16 ) >= *lpz )
				{
#if BOUNDCHECK_MODE == 1
					if( !R_DrawCheckBounds( (pixel_t *)base16 + ( lp8 - base8 )))
						return;
#endif
					pixel_t src = pal[*lp8];
					if( src != TRANSPARENT_COLOR )
					{
						*lpdest = vid.colormap[( src >> 3 ) | (( llight & 0x1F00 ) << 5 )] | ( src & 7 );
						*lpz = lzi >> 16;
					}
				}
				lpdest++;
				lzi += r_zistepx;
				lpz++;
				llight += r_lstepx;
				lp8 += a_ststepxwhole;
				lsfrac += a_sstepxfrac;
				lp8 += lsfrac >> 16;
				lsfrac &= 0xFFFF;
				ltfrac += a_tstepxfrac;
				if( ltfrac & 0x10000 )
				{
					lp8 += skinwidth;
					ltfrac &= 0xFFFF;
				}
			}
			while( --lcount );
		}
		else
			pspanpackage++;
	}
	while( pspanpackage->count != -999999 );
}
'''
def skin_i8_polyse(t):
    if "LR_SKIN_I8" in t:
        return t
    return t + FILL_I8
patch("ref/soft/r_polyse.c", skin_i8_polyse)

def skin_i8_header(t):
    if "R_PolysetFillSpans8_I8" in t:
        return t
    old = "void R_PolysetFillSpans8( spanpackage_t * );\n"
    assert old in t
    return t.replace(old, old + "void R_PolysetFillSpans8_I8( spanpackage_t * );\nextern pixel_t *r_skinpal8;\n", 1)
patch("ref/soft/r_local.h", skin_i8_header)

def skin_i8_bind(t):
    if "LR_SKIN_I8" in t:
        return t
    old = "\tif( vid.rendermode == kRenderNormal )\n\t{\n\t\tr_affinetridesc.pskin = R_TexPixels( image );\n\t\td_pdrawspans = R_PolysetFillSpans8;\n\t}\n"
    assert old in t
    new = ("\tif( vid.rendermode == kRenderNormal && !image->pixels[0] && image->idx[0] )\n\t{\t// LR_SKIN_I8\n"
           "\t\tr_affinetridesc.pskin = image->idx[0];\n\t\tr_skinpal8 = image->pal8;\n\t\td_pdrawspans = R_PolysetFillSpans8_I8;\n\t}\n\telse " + old[1:])
    return t.replace(old, new, 1)
patch("ref/soft/r_image.c", skin_i8_bind)

# the studio fast path (29) must accept the I8 fill too
def studio_fast_i8(t):
    old = "d_pdrawspans == R_PolysetFillSpans8 && !vid.is2d"
    if old not in t:
        return t
    return t.replace(old, "( d_pdrawspans == R_PolysetFillSpans8 || d_pdrawspans == R_PolysetFillSpans8_I8 ) && !vid.is2d", 1)
patch("ref/soft/r_studio.c", studio_fast_i8)

# 32. memory + speed: the 1.5 MB alpha blend table (vid.alphamap) is replaced by arithmetic. The renderer's
# pixel format is a bit permutation of RGB565, so it converts with two 256-entry tables each way (2 KB, stays in
# the L1 cache), blends two RGB565 pixels in one register (SWAR) and converts back. Weights are the ones the
# table used: alpha 1..3 -> (alpha+1)/7 of the source, 4..6 -> (alpha-1)/7.
BLEND_FN = r'''
// R36HD LR_ALPHA_ARITH: see r_glblit.c R_BuildBlendMaps
extern unsigned short r_dec_hi[256], r_dec_lo[256], r_enc_hi[256], r_enc_lo[256];
static inline pixel_t LR_BlendAlpha( int alpha, pixel_t src, pixel_t dst )
{
	static const unsigned char w32[8] = { 0, 9, 14, 18, 14, 18, 23, 32 };
	unsigned s = r_dec_hi[src >> 8] | r_dec_lo[src & 0xff];
	unsigned d = r_dec_hi[dst >> 8] | r_dec_lo[dst & 0xff];
	unsigned xs = ( s | s << 16 ) & 0x07E0F81Fu, xd = ( d | d << 16 ) & 0x07E0F81Fu;
	unsigned x = ( xd + ((( xs - xd ) * w32[alpha & 7] ) >> 5 )) & 0x07E0F81Fu;
	x = ( x | x >> 16 ) & 0xFFFF;
	return r_enc_hi[x >> 8] | r_enc_lo[x & 0xff];
}
#define BLEND_ALPHA( alpha, src, dst )        LR_BlendAlpha(( alpha ), ( src ), ( dst ))
'''
def alpha_arith_h(t):
    if "LR_ALPHA_ARITH" in t:
        return t
    old_tab = "\tpixel_t      alphamap[3 * 1024 * 256];\n"
    assert old_tab in t
    t = t.replace(old_tab, "\t// alphamap removed (LR_ALPHA_ARITH)\n", 1)
    old = ("#define BLEND_ALPHA_LOW( alpha, src, screen ) ( vid.alphamap[(( alpha ) << 18 ) | ((( src ) & 0xff00 ) << 2 ) | (( screen ) >> 6 )] | (( screen ) & 0x3f ))\n"
           "#define BLEND_ALPHA( alpha, src, dst )        ( alpha ) > 3 ? BLEND_ALPHA_LOW( 7 - 1 - ( alpha ), ( dst ), ( src )) : BLEND_ALPHA_LOW(( alpha ) - 1, ( src ), ( dst ))\n")
    assert old in t
    return t.replace(old, BLEND_FN, 1)
patch("ref/soft/r_local.h", alpha_arith_h)

def alpha_arith_c(t):
    if "LR_ALPHA_ARITH" in t:
        return t
    a = t.index("\tfor( unsigned int i = 0; i < 1024; i++ )\n\t{\n\t\tunsigned int   r, g, b;\n\t\tuint           color = i << 6 | BIT( 5 ) | BIT( 4 ) | BIT( 3 );")
    b = t.index("\t\t\t\tvid.alphamap[k << 18 | index2 | index1] = major << 8 | ( minor & 0xFF );\n\t\t\t}\n\t\t}\n\t}\n", a)
    b += len("\t\t\t\tvid.alphamap[k << 18 | index2 | index1] = major << 8 | ( minor & 0xFF );\n\t\t\t}\n\t\t}\n\t}\n")
    new = r'''	// LR_ALPHA_ARITH: renderer pixel <-> RGB565, one table per byte (the format is a bit permutation)
	for( unsigned int i = 0; i < 256; i++ )
	{
		unsigned int r, g, b, major, minor;
		r = (( i >> 5 ) & 7 ) << 2; g = (( i >> 2 ) & 7 ) << 3; b = ( i & 3 ) << 3;      // major byte
		r_dec_hi[i] = r << 11 | g << 5 | b;
		r = MOVE_BIT( i, 5, 1 ) | MOVE_BIT( i, 2, 0 );                                  // minor GBRGBRGB
		g = MOVE_BIT( i, 7, 2 ) | MOVE_BIT( i, 4, 1 ) | MOVE_BIT( i, 1, 0 );
		b = MOVE_BIT( i, 6, 2 ) | MOVE_BIT( i, 3, 1 ) | MOVE_BIT( i, 0, 0 );
		r_dec_lo[i] = r << 11 | g << 5 | b;
		// RGB565 high byte (r5 g6 top 3) and low byte (g6 low 3, b5) -> renderer pixel
		r = i >> 3; g = ( i & 7 ) << 3; b = 0;
		major = ((( r >> 2 ) & MASK( 3 )) << 5 ) | (((( g >> 3 ) & MASK( 3 )) << 2 )) | ((( b >> 3 ) & MASK( 2 )));
		minor = MOVE_BIT( r, 1, 5 ) | MOVE_BIT( r, 0, 2 ) | MOVE_BIT( g, 2, 7 ) | MOVE_BIT( g, 1, 4 ) | MOVE_BIT( g, 0, 1 ) | MOVE_BIT( b, 2, 6 ) | MOVE_BIT( b, 1, 3 ) | MOVE_BIT( b, 0, 0 );
		r_enc_hi[i] = major << 8 | ( minor & 0xFF );
		r = 0; g = i >> 5; b = i & 31;
		major = ((( r >> 2 ) & MASK( 3 )) << 5 ) | (((( g >> 3 ) & MASK( 3 )) << 2 )) | ((( b >> 3 ) & MASK( 2 )));
		minor = MOVE_BIT( r, 1, 5 ) | MOVE_BIT( r, 0, 2 ) | MOVE_BIT( g, 2, 7 ) | MOVE_BIT( g, 1, 4 ) | MOVE_BIT( g, 0, 1 ) | MOVE_BIT( b, 2, 6 ) | MOVE_BIT( b, 1, 3 ) | MOVE_BIT( b, 0, 0 );
		r_enc_lo[i] = major << 8 | ( minor & 0xFF );
	}
'''
    t = t[:a] + new + t[b:]
    t = t.replace("static void R_BuildBlendMaps( void )\n", "unsigned short r_dec_hi[256], r_dec_lo[256], r_enc_hi[256], r_enc_lo[256];\nstatic void R_BuildBlendMaps( void )\n", 1)
    return t
patch("ref/soft/r_glblit.c", alpha_arith_c)

# 33. speed: blit in whole 32-byte cache lines. The destination line is fully written, so "pref 30"
# (PrepareForStore) lets the 74K allocate it without reading it from memory first; the source is prefetched
# two lines ahead. Needs 32-byte aligned rows (vid_libretro.c allocates them so).
BLIT_LINES = r'''				int n = vid.width >> 1;
				// LR_BLIT_LINES
				if( lr_split && !( n & 7 ) && !((uintptr_t)dst & 31 ))
				{
					for( int u = 0; u < n; u += 8 )
					{
#if defined( __mips__ )
						__asm__ volatile( "pref 30, 0(%0)" : : "r"( dst + u ));
						__asm__ volatile( "pref 0, 64(%0)" : : "r"( src + u ));
#endif
						for( int k = 0; k < 8; k++ )
						{
							uint32_t p = src[u + k];
							dst[u + k] = ( lr_scr_hi[( p >> 8 ) & 0xff] | lr_scr_lo[p & 0xff] ) | (( lr_scr_hi[p >> 24] | lr_scr_lo[( p >> 16 ) & 0xff] ) << 16 );
						}
					}
					continue;
				}
'''
def blit_lines(t):
    if "LR_BLIT_LINES" in t:
        return t
    old = "\t\t\t\tint n = vid.width >> 1;\n"
    assert t.count(old) == 1
    return t.replace(old, BLIT_LINES, 1)
patch("ref/soft/r_glblit.c", blit_lines)

# 34. speed: two message buffers were cleared in full for every packet (64 KB in Netchan_TransmitBits and 4 KB
# in SV_SendClientDatagram, about 6000 cache lines a frame on the device). The bit writer only needs zeroed
# memory, so the buffers are static, start zeroed, and after each packet only the bytes written are cleared.
def netchan_clear(t):
    if "LR_NETCLEAR" in t:
        return t
    old = "\tbyte\tsend_buf[NET_MAX_MESSAGE];\n"
    assert old in t
    t = t.replace(old, "\tstatic byte\tsend_buf[NET_MAX_MESSAGE]; // LR_NETCLEAR: zero on entry, used part cleared at the end\n", 1)
    old = "\tmemset( send_buf, 0, sizeof( send_buf ));\n\tMSG_Init( &send, \"NetSend\", send_buf, sizeof( send_buf ));\n"
    assert old in t
    t = t.replace(old, "\tMSG_Init( &send, \"NetSend\", send_buf, sizeof( send_buf ));\n", 1)
    old = """			, send_reliable ? 1 : 0
			, (float)host.realtime );
	}
}
"""
    assert old in t
    t = t.replace(old, """			, send_reliable ? 1 : 0
			, (float)host.realtime );
	}
	{
		size_t used = (size_t)MSG_GetNumBytesWritten( &send ) + 8;
		memset( send_buf, 0, used < sizeof( send_buf ) ? used : sizeof( send_buf ));
	}
}
""", 1)
    return t
patch("engine/common/net_chan.c", netchan_clear)

def datagram_clear(t):
    if "LR_NETCLEAR" in t:
        return t
    old = """	byte	msg_buf[MAX_DATAGRAM];
	sizebuf_t	msg;

	memset( msg_buf, 0, sizeof( msg_buf ));
	MSG_Init( &msg, "Datagram", msg_buf, sizeof( msg_buf ));
"""
    assert old in t
    t = t.replace(old, """	static byte	msg_buf[MAX_DATAGRAM]; // LR_NETCLEAR: zero on entry, used part cleared at the end
	sizebuf_t	msg;
	qboolean	lr_full = false;

	MSG_Init( &msg, "Datagram", msg_buf, sizeof( msg_buf ));
""", 1)
    old = """		Con_Printf( S_ERROR "%s overflowed for %s\\n", MSG_GetName( &msg ), cl->name );
		MSG_Clear( &msg );
	}

	// send the datagram
	Netchan_TransmitBits( &cl->netchan, MSG_GetNumBitsWritten( &msg ), MSG_GetData( &msg ));
}
"""
    assert old in t, "datagram tail"
    t = t.replace(old, """		Con_Printf( S_ERROR "%s overflowed for %s\\n", MSG_GetName( &msg ), cl->name );
		MSG_Clear( &msg );
		lr_full = true;
	}

	// send the datagram
	Netchan_TransmitBits( &cl->netchan, MSG_GetNumBitsWritten( &msg ), MSG_GetData( &msg ));
	{
		size_t used = lr_full ? sizeof( msg_buf ) : (size_t)MSG_GetNumBytesWritten( &msg ) + 8;
		memset( msg_buf, 0, used < sizeof( msg_buf ) ? used : sizeof( msg_buf ));
	}
}
""", 1)
    return t
patch("engine/server/sv_frame.c", datagram_clear)

# 35. speed: D_DrawSpans16 inner loop: globals copied to locals (a 32-bit store may alias them, so GCC
# reloaded them per pixel), two pixels per 32-bit store, and "pref 30" when a 16-pixel run fills one whole
# 32-byte cache line. D_DrawZSpans: pref 30 for every whole line it writes. Same pixels and z values as before.
SPAN_LOOP_OLD = """			// Drawing phrase
			if( !SW_TEXFILT )
			{
				do
				{
					*pdest++ = pbase[( s >> 16 ) + ( t >> 16 ) * cachewidth];
					s += sstep;
					t += tstep;
				}
				while( --spancount > 0 );
			}
"""
SPAN_LOOP_NEW = """			// Drawing phrase
			if( !SW_TEXFILT )
			{	// LR_SPANLOOP
				const pixel_t *tb = pbase;
				const int     cw = cachewidth;
				int           ls = s, lt = t;
				const int     ss = sstep, ts = tstep;
				int           n = spancount;
#if defined( __mips__ )
				if( n == 16 && !((uintptr_t)pdest & 31 ) )
					__asm__ volatile( "pref 30, 0(%0)" : : "r"( pdest ));
#endif
				if((uintptr_t)pdest & 2 )
				{
					*pdest++ = tb[( ls >> 16 ) + ( lt >> 16 ) * cw];
					ls += ss; lt += ts; n--;
				}
				while( n >= 2 )
				{
					uint32_t p0 = tb[( ls >> 16 ) + ( lt >> 16 ) * cw];
					ls += ss; lt += ts;
					uint32_t p1 = tb[( ls >> 16 ) + ( lt >> 16 ) * cw];
					ls += ss; lt += ts;
					*(uint32_t *)pdest = p0 | p1 << 16;
					pdest += 2; n -= 2;
				}
				if( n )
				{
					*pdest++ = tb[( ls >> 16 ) + ( lt >> 16 ) * cw];
					ls += ss; lt += ts;
				}
				s = ls; t = lt;
			}
"""
ZSPAN_OLD = """		int doublecount;
		if(( doublecount = count >> 1 ) > 0 )
		{
			do
			{
				unsigned ltemp = izi >> 16;
				izi += izistep;
				ltemp |= izi & 0xFFFF0000;
				izi += izistep;
				*(int *)pdest = ltemp;
				pdest += 2;
			}
			while( --doublecount > 0 );
		}
"""
ZSPAN_NEW = """		int doublecount;
		if(( doublecount = count >> 1 ) > 0 )
		{	// LR_ZSPANLOOP: whole 32-byte lines are allocated without a read (pref 30)
			while( doublecount > 0 )
			{
#if defined( __mips__ )
				if( !((uintptr_t)pdest & 31 ) && doublecount >= 8 )
					__asm__ volatile( "pref 30, 0(%0)" : : "r"( pdest ));
#endif
				unsigned ltemp = izi >> 16;
				izi += izistep;
				ltemp |= izi & 0xFFFF0000;
				izi += izistep;
				*(int *)pdest = ltemp;
				pdest += 2;
				doublecount--;
			}
		}
"""
def span_loops(t):
    if "LR_SPANLOOP" in t:
        return t
    assert SPAN_LOOP_OLD in t and ZSPAN_OLD in t
    t = t.replace(SPAN_LOOP_OLD, SPAN_LOOP_NEW, 1)
    t = t.replace(ZSPAN_OLD, ZSPAN_NEW, 1)
    return t
patch("ref/soft/r_scan.c", span_loops)

# 36. speed: beam noise used the engine's random generator (Park-Miller with divisions, 127 calls per beam
# per frame). Beams only need visual noise: a local xorshift generator, same range.
def beam_noise(t):
    if "LR_BEAMRNG" in t:
        return t
    old = "\tnoise[div2] = ( noise[0] + noise[divs] ) * 0.5f + divs * gEngfuncs.COM_RandomFloat( -0.125f, 0.125f );\n"
    assert old in t
    new = ("\t// LR_BEAMRNG\n\tstatic uint32_t lr_rng = 0x9E3779B9u;\n"
           "\tlr_rng ^= lr_rng << 13; lr_rng ^= lr_rng >> 17; lr_rng ^= lr_rng << 5;\n"
           "\tnoise[div2] = ( noise[0] + noise[divs] ) * 0.5f + divs * (( lr_rng >> 8 ) * ( 0.25f / 16777216.0f ) - 0.125f );\n")
    return t.replace(old, new, 1)
patch("ref/soft/r_beams.c", beam_noise)

# 37. speed: TriBrightness is called for every beam vertex with the same values; remember the last result
def tribright_memo(t):
    if "LR_BRIGHTMEMO" in t:
        return t
    old = """void TriBrightness( float brightness )
{
	float r = ds.triRGBA[0] * ds.triRGBA[3] * brightness;
	float g = ds.triRGBA[1] * ds.triRGBA[3] * brightness;
	float b = ds.triRGBA[2] * ds.triRGBA[3] * brightness;

	_TriColor4f( r, g, b, 1.0f );
}"""
    assert old in t
    new = """void TriBrightness( float brightness )
{
	// LR_BRIGHTMEMO: same inputs -> same outputs of _TriColor4f (light, vid.color, vid.alpha)
	static float lb = -1.0f, lr, lg, lbb, la; static int lmode = -1, l2d = -1;
	static uint ol; static pixel_t ocol; static byte oalpha;
	if( brightness == lb && ds.triRGBA[0] == lr && ds.triRGBA[1] == lg && ds.triRGBA[2] == lbb && ds.triRGBA[3] == la
		&& vid.rendermode == lmode && vid.is2d == l2d )
	{
		light = ol;
		if( !( !vid.is2d && vid.rendermode == kRenderNormal )) { vid.color = ocol; vid.alpha = oalpha; }
		return;
	}
	float r = ds.triRGBA[0] * ds.triRGBA[3] * brightness;
	float g = ds.triRGBA[1] * ds.triRGBA[3] * brightness;
	float b = ds.triRGBA[2] * ds.triRGBA[3] * brightness;

	_TriColor4f( r, g, b, 1.0f );
	lb = brightness; lr = ds.triRGBA[0]; lg = ds.triRGBA[1]; lbb = ds.triRGBA[2]; la = ds.triRGBA[3];
	lmode = vid.rendermode; l2d = vid.is2d;
	ol = light; ocol = vid.color; oalpha = vid.alpha;
}"""
    return t.replace(old, new, 1)
patch("ref/soft/r_triapi.c", tribright_memo)

# 38. speed: R_RecursiveClipBPoly computed the plane distance of each vertex twice (an edge starts where the
# previous one ended); reuse it when the start vertex is the previous end vertex. Same values.
def bpoly_dist(t):
    if "LR_BPOLYDIST" in t:
        return t
    old = """		plastvert = pedges->v[0];
		lastdist = DotProduct( plastvert->position, tplane.normal )
			   - tplane.dist;
"""
    assert old in t
    new = """		plastvert = pedges->v[0];
		if( plastvert == lr_prevvert ) lastdist = lr_prevdist; // LR_BPOLYDIST
		else lastdist = DotProduct( plastvert->position, tplane.normal )
			   - tplane.dist;
"""
    t = t.replace(old, new, 1)
    old = """		dist = DotProduct( pvert->position, tplane.normal ) - tplane.dist;
"""
    assert old in t
    t = t.replace(old, old + "\t\tlr_prevvert = pvert; lr_prevdist = dist;\n", 1)
    old = "// clip edges to BSP plane\n\tfor( ; pedges; pedges = pnextedge )\n"
    assert old in t
    t = t.replace(old, "\tconst mvertex_t *lr_prevvert = NULL; float lr_prevdist = 0;\n" + old, 1)
    return t
patch("ref/soft/r_bsp.c", bpoly_dist)

# 39. speed: ref_soft never culled beams (R_BeamCull returned false), so beams behind walls or behind the
# player were built and clipped every frame. Same test as the GL renderer for the PVS, plus "box entirely
# behind the view plane" instead of its frustum test. The box is padded by 32 units for beam noise.
def beam_cull(t):
    if "LR_BEAMCULL" in t:
        return t
    old = """static qboolean R_BeamCull( const vec3_t start, const vec3_t end, qboolean pvsOnly )
{
	// culling is undone in ref_soft
	return false;
}"""
    assert old in t
    new = """static qboolean R_BeamCull( const vec3_t start, const vec3_t end, qboolean pvsOnly )
{
	// LR_BEAMCULL
	vec3_t mins, maxs;
	int i, k;
	for( i = 0; i < 3; i++ )
	{
		mins[i] = Q_min( start[i], end[i] ) - 32.0f;
		maxs[i] = Q_max( start[i], end[i] ) + 32.0f;
	}
	if( !WORLDMODEL ) return false;
	if( !gEngfuncs.Mod_BoxVisible( mins, maxs, Mod_GetCurrentVis( )))
		return true;
	if( pvsOnly ) return false;
	for( k = 0; k < 8; k++ )
	{
		vec3_t p;
		p[0] = ( k & 1 ) ? maxs[0] : mins[0];
		p[1] = ( k & 2 ) ? maxs[1] : mins[1];
		p[2] = ( k & 4 ) ? maxs[2] : mins[2];
		VectorSubtract( p, RI.rvp.vieworigin, p );
		if( DotProduct( p, RI.vforward ) > 0.0f ) return false;   // a corner is in front of the viewer
	}
	return true;
}"""
    return t.replace(old, new, 1)
patch("ref/soft/r_beams.c", beam_cull)

# 40. build: libbacktrace's elf.c needs struct dl_phdr_info, which <link.h> only declares when __USE_GNU is set.
# The forced -include of fastmath.h pulls <math.h> in before config.h can define _GNU_SOURCE, so it never is.
def backtrace_gnu(t):
    old = "#ifdef HAVE_DL_ITERATE_PHDR\n #ifdef HAVE_LINK_H\n"
    if "LR_GNU" in t:
        return t
    assert old in t
    return t.replace(old, "#ifndef __USE_GNU\n#define __USE_GNU 1 /* LR_GNU */\n#endif\n" + old, 1)
patch("3rdparty/libbacktrace/libbacktrace/elf.c", backtrace_gnu)
