/*
vid_libretro.c - video for the libretro core: ref_soft blits into an RGB565 buffer that the core hands to picoarch.
Replaces engine/platform/linux/vid_fbdev.c (same backend slot, XASH_VIDEO == VIDEO_FBDEV).
Two buffers alternate on every finished frame, so the one picoarch is showing is never drawn into.
Menus, the console and loading screens are drawn at a higher resolution (HL_MENU_RES, default 640x480) so their
text can be read; the game itself runs at the core option's resolution.
*/
#include "platform/platform.h"
#if XASH_VIDEO == VIDEO_FBDEV
#include "input.h"
#include "client.h"
#include "filesystem.h"
#include "vid_common.h"
#include "hl_libretro.h"

static uint16_t *lr_fb[2];
static uint16_t *lr_old[2];      // previous size's buffers: freed only at the next resize (picoarch may still show one)
static int lr_draw;              // buffer being drawn
static int lr_w = 256, lr_h = 192;          // current render size
static int lr_game_w = 256, lr_game_h = 192;
static int lr_menu_w = 640, lr_menu_h = 480;

void LR_SetVideoSize( int w, int h )
{
	lr_w = lr_game_w = w; lr_h = lr_game_h = h;
	const char *m = getenv( "HL_MENU_RES" );
	if( m && sscanf( m, "%dx%d", &lr_menu_w, &lr_menu_h ) != 2 ) { lr_menu_w = 640; lr_menu_h = 480; }
	if( lr_menu_w < w || lr_menu_h < h ) { lr_menu_w = w; lr_menu_h = h; }
}

// once per engine loop (LR_Sync): pick the size for what is on screen
void LR_CheckVideoSize( void )
{
	if( !ref.initialized ) return;
	qboolean menu = cls.key_dest == key_menu || cls.key_dest == key_console || cls.state != ca_active;
	int w = menu ? lr_menu_w : lr_game_w, h = menu ? lr_menu_h : lr_game_h;
	if( w == lr_w && h == lr_h ) return;
	lr_w = w; lr_h = h;
	R_SaveVideoMode( w, h, w, h, false );   // the renderer reallocates its buffers at the next blit
}

void Platform_Minimize_f( void ) { }
void GL_SwapBuffers( void ) { }

qboolean R_Init_Video( ref_graphic_apis_t type )
{
	if( type != REF_SOFTWARE )
		return false;
	if( !VID_SetMode( ))
		return false;
	host.renderinfo_changed = false;
	return true;
}

void R_Free_Video( void )
{
	ref.dllFuncs.GL_ClearExtensions();
}

qboolean VID_SetMode( void )
{
	R_ChangeDisplaySettings( 0, 0, WINDOW_MODE_FULLSCREEN );
	return true;
}

rserr_t R_ChangeDisplaySettings( int width, int height, window_mode_t window_mode )
{
	int render_w = lr_w, render_h = lr_h;
	width = lr_w; height = lr_h;
	VID_SetDisplayTransform( &render_w, &render_h );
	R_SaveVideoMode( width, height, render_w, render_h, false );
	return rserr_ok;
}

int GL_SetAttribute( int attr, int val ) { return 0; }
int GL_GetAttribute( int attr, int *val ) { return 0; }
int R_MaxVideoModes( void ) { return 0; }
vidmode_t *R_GetVideoMode( int num ) { return NULL; }
void *GL_GetProcAddress( const char *name ) { return NULL; }
void GL_UpdateSwapInterval( void ) { }

static int lr_buf_w, lr_buf_h;

void *SW_LockBuffer( void )
{
	return lr_fb[lr_draw];
}

static int lr_old_age;           // frames shown since the last resize

void SW_UnlockBuffer( void )
{
	LR_FrameReady( lr_fb[lr_draw], lr_buf_w, lr_buf_h );
	lr_draw ^= 1;
	// two new frames went out since the resize, so picoarch no longer shows an old-size buffer: give the
	// memory back (2 x 600 KB after a 640x480 menu)
	if( lr_old[0] && ++lr_old_age >= 3 )
	{
		free( lr_old[0] ); free( lr_old[1] );
		lr_old[0] = lr_old[1] = NULL;
	}
}

qboolean SW_CreateBuffer( int width, int height, uint *stride, uint *bpp, uint *r, uint *g, uint *b )
{
	for( int i = 0; i < 2; i++ )
	{
		free( lr_old[i] );
		lr_old[i] = lr_fb[i];
		// 32-byte aligned rows: the blit writes whole cache lines (pref 30)
		void *p = NULL;
		if( posix_memalign( &p, 32, (size_t)width * height * 2 ) != 0 ) return false;
		memset( p, 0, (size_t)width * height * 2 );
		lr_fb[i] = p;
	}
	lr_old_age = 0;
	lr_buf_w = width; lr_buf_h = height;
	*bpp = 2;
	*stride = width;
	*r = 0xF800; *g = 0x07E0; *b = 0x001F;
	return true;
}

ref_window_type_t R_GetWindowHandle( void **handle, ref_window_type_t type )
{
	return REF_WINDOW_TYPE_NULL;
}

platform_orientation_t Platform_GetDisplayOrientation( void )
{
	return ORIENTATION_LANDSCAPE;
}

void VID_Info_f( void )
{
	Con_Printf( "libretro video: %dx%d RGB565 (game %dx%d, menus %dx%d)\n", lr_w, lr_h, lr_game_w, lr_game_h, lr_menu_w, lr_menu_h );
}

#endif
