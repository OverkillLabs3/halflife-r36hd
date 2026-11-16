/*
hl_core.c - libretro front end for Half-Life (Xash3D FWGS + hlsdk-portable, all linked into one core).

The engine's own main loop runs on a worker thread. Each loop iteration calls LR_Sync(), which hands control
back to retro_run and waits; retro_run lets exactly one iteration run per call (lock step, no busy waiting, one
CPU core). A finished frame is handed over in SW_UnlockBuffer; when an iteration produced no new frame,
retro_run passes NULL so picoarch shows the previous one without the cost of a new blit.
Sound: 22050 Hz stereo, taken from the engine's ring buffer for the real time that passed.
*/
#define _GNU_SOURCE
#include <pthread.h>
#include <semaphore.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include <time.h>
#include <unistd.h>
#include <malloc.h>
#include <sys/stat.h>
#include <dirent.h>
#include <strings.h>
#include <dlfcn.h>
#include "libretro.h"
#include "hl_libretro.h"
#include "../../common/crashlog.c"
#include "../../common/mmz_heap.c"   /* heap in the idle video pool, see common/mmz_heap.h */

#ifndef LR_GAMEDIR
#define LR_GAMEDIR "valve"      // game folder; other mods build the core with -DLR_GAMEDIR=\"name\"
#endif
#define AUDIO_RATE 22050
#define CORE_FPS 60.0

int Host_Main( int argc, char **argv, const char *progname, int bChangeGame, void *pChangeGame );

static retro_video_refresh_t video_cb;
static retro_audio_sample_batch_t audio_cb;
static retro_input_poll_t input_poll_cb;
static retro_input_state_t input_state_cb;
static retro_environment_t env_cb;

static sem_t sem_go, sem_done;
static pthread_t game_thread;
static volatile int game_running, game_ended, game_started;
static const uint16_t *volatile fresh_frame;
static const uint16_t *last_frame;
static int frame_w = 256, frame_h = 192;
static char base_dir[512];
static uint16_t black[256 * 192];

static double now_s( void ) { struct timespec t; clock_gettime( CLOCK_MONOTONIC, &t ); return t.tv_sec + t.tv_nsec * 1e-9; }

// ---- engine -> core
void LR_FrameReady( const uint16_t *pixels, int w, int h )
{
	fresh_frame = pixels;
	frame_w = w; frame_h = h;
}

void LR_CheckVideoSize( void );

void LR_Sync( void )
{
	static int frames;
	if( ++frames % 300 == 0 ) malloc_trim( 0 );
	LR_CheckVideoSize( );
	sem_post( &sem_done );
	while( sem_wait( &sem_go ) != 0 && errno == EINTR ) { }
}

// ---- core options
static const char *core_option( const char *key )
{
	struct retro_variable v = { key, 0 };
	if( env_cb && env_cb( RETRO_ENVIRONMENT_GET_VARIABLE, &v ) && v.value ) return v.value;
	return 0;
}

void retro_set_environment( retro_environment_t cb )
{
	env_cb = cb;
	bool no_game = false;
	cb( RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME, &no_game );
	static const struct retro_variable vars[] = {
		{ "hl_resolution", "Render resolution (restart); 256x192|320x240|400x300" },
		{ "hl_start", "At start (restart); continue|newgame|menu" },
		{ "hl_fps_overlay", "FPS counter; on|off" },
		{ NULL, NULL },
	};
	cb( RETRO_ENVIRONMENT_SET_VARIABLES, (void *)vars );
}
void retro_set_video_refresh( retro_video_refresh_t cb ) { video_cb = cb; }
void retro_set_audio_sample( retro_audio_sample_t cb ) { (void)cb; }
void retro_set_audio_sample_batch( retro_audio_sample_batch_t cb ) { audio_cb = cb; }
void retro_set_input_poll( retro_input_poll_t cb ) { input_poll_cb = cb; }
void retro_set_input_state( retro_input_state_t cb ) { input_state_cb = cb; }

void retro_get_system_info( struct retro_system_info *info )
{
	memset( info, 0, sizeof( *info ));
	info->library_name = "Half-Life (Xash3D FWGS)";
	info->library_version = "0.1";
	info->valid_extensions = "hl";
	info->need_fullpath = true;
	info->block_extract = true;
}

void retro_get_system_av_info( struct retro_system_av_info *info )
{
	memset( info, 0, sizeof( *info ));
	info->geometry.base_width = frame_w;
	info->geometry.base_height = frame_h;
	info->geometry.max_width = 400;
	info->geometry.max_height = 300;
	info->geometry.aspect_ratio = 4.0f / 3.0f;
	info->timing.fps = CORE_FPS;
	info->timing.sample_rate = AUDIO_RATE;
}

void retro_init( void ) { }
void retro_deinit( void ) { }
unsigned retro_api_version( void ) { return RETRO_API_VERSION; }
void retro_set_controller_port_device( unsigned port, unsigned device ) { (void)port; (void)device; }
void retro_reset( void ) { }
size_t retro_serialize_size( void ) { return 0; }
bool retro_serialize( void *data, size_t size ) { (void)data; (void)size; return false; }
bool retro_unserialize( const void *data, size_t size ) { (void)data; (void)size; return false; }
void retro_cheat_reset( void ) { }
void retro_cheat_set( unsigned index, bool enabled, const char *code ) { (void)index; (void)enabled; (void)code; }
unsigned retro_get_region( void ) { return RETRO_REGION_NTSC; }
void *retro_get_memory_data( unsigned id ) { (void)id; return NULL; }
size_t retro_get_memory_size( unsigned id ) { (void)id; return 0; }
bool retro_load_game_special( unsigned type, const struct retro_game_info *info, size_t num ) { (void)type; (void)info; (void)num; return false; }

// pad bindings and settings for this device; executed by the engine after config.cfg (userconfig.d)
static void write_pad_config( void )
{
	char path[600];
	snprintf( path, sizeof( path ), "%s/" LR_GAMEDIR "/userconfig.d", base_dir );
	mkdir( path, 0755 );
	snprintf( path, sizeof( path ), "%s/" LR_GAMEDIR "/userconfig.d/r36hd.cfg", base_dir );
	FILE *f = fopen( path, "w" );
	if( !f ) return;
	fputs( "// written by halflife_libretro.so at every start: R36HD pad and speed settings\n"
		"bind UPARROW +forward\nbind DOWNARROW +back\nbind LEFTARROW +moveleft\nbind RIGHTARROW +moveright\n"
		"bind MOUSE1 +attack\nbind MOUSE2 +attack2\nbind SPACE +jump\nbind e +use\nbind CTRL +duck\n"
		"bind r +reload\nbind f impulse 100\nbind MWHEELUP invprev\nbind MWHEELDOWN invnext\n"
		"bind F6 \"save quick\"\nbind F9 \"load quick\"\nbind ENTER +attack\n"
		// fps_max 0: the frontend paces retro_run and each call must produce a frame (a 60 limit dropped a third of them)
		"hud_fastswitch 1\nfps_max 0\ncl_showfps 0\nm_ignore 0\nsleeptime 0\n", f );
	fclose( f );
}

static void *game_main( void *arg )
{
	(void)arg;
	static char *argv[32];
	int argc = 0;
	argv[argc++] = "xash";
	{
		// the menu is unreadable at this size: go straight into the game. Newest save if there is one
		// (core option hl_start: continue | newgame | menu), else a new game.
		const char *mode = core_option( "hl_start" );
		static char load[300];
		if( !mode || !strcmp( mode, "continue" ))
		{
			char dir[600];
			snprintf( dir, sizeof dir, "%s/" LR_GAMEDIR "/save", base_dir );
			DIR *d = opendir( dir );
			if( !d ) { snprintf( dir, sizeof dir, "%s/" LR_GAMEDIR "/SAVE", base_dir ); d = opendir( dir ); }
			time_t best = 0;
			if( d )
			{
				struct dirent *e;
				while(( e = readdir( d )))
				{
					size_t n = strlen( e->d_name );
					if( n < 5 || strcasecmp( e->d_name + n - 4, ".sav" )) continue;
					char p[900]; struct stat st;
					snprintf( p, sizeof p, "%s/%s", dir, e->d_name );
					if( stat( p, &st ) == 0 && st.st_mtime > best )
					{
						best = st.st_mtime;
						snprintf( load, sizeof load, "%.*s", (int)( n - 4 ), e->d_name );
					}
				}
				closedir( d );
			}
			if( best ) { argv[argc++] = "+load"; argv[argc++] = load; }
			else mode = "newgame";
		}
		if( mode && !strcmp( mode, "newgame" )) { argv[argc++] = "+map"; argv[argc++] = "c0a0"; }
	}
	argv[argc] = NULL;
	Host_Main( argc, argv, LR_GAMEDIR, 0, NULL );
	game_ended = 1;
	sem_post( &sem_done );
	return NULL;
}

bool retro_load_game( const struct retro_game_info *game )
{
	enum retro_pixel_format fmt = RETRO_PIXEL_FORMAT_RGB565;
	if( !env_cb || !env_cb( RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &fmt )) return false;

	// content = <port dir>/<marker>; the game data sits in <port dir>/valve
	if( game && game->path )
	{
		snprintf( base_dir, sizeof( base_dir ), "%s", game->path );
		char *s = strrchr( base_dir, '/' );
		if( s ) *s = 0; else strcpy( base_dir, "." );
	}
	else strcpy( base_dir, "." );
	setenv( "XASH3D_BASEDIR", base_dir, 1 );
	if( chdir( base_dir ) != 0 ) { }

	int w = 256, h = 192;
	const char *r = core_option( "hl_resolution" );
	if( r && sscanf( r, "%dx%d", &w, &h ) != 2 ) { w = 256; h = 192; }
	frame_w = w; frame_h = h;
	LR_SetVideoSize( w, h );

	mallopt( M_ARENA_MAX, 1 );
	mallopt( M_MMAP_THRESHOLD, 128 * 1024 );
	mallopt( M_TRIM_THRESHOLD, 128 * 1024 );
	crashlog_install("halflife");
	mmz_heap_install();
	write_pad_config( );

	sem_init( &sem_go, 0, 0 );
	sem_init( &sem_done, 0, 0 );
	pthread_attr_t attr;
	pthread_attr_init( &attr );
	pthread_attr_setstacksize( &attr, 2u * 1024 * 1024 );
	if( pthread_create( &game_thread, &attr, game_main, NULL ) != 0 ) return false;
	game_running = 1;
	// wait for the engine to finish starting (its first LR_Sync)
	while( sem_wait( &sem_done ) != 0 && errno == EINTR ) { }
	game_started = 1;
	return !game_ended;
}

void retro_unload_game( void ) { }

static void read_pad( void )
{
	uint32_t p = 0;
	input_poll_cb( );
	for( unsigned id = 0; id < 16; id++ )
		if( input_state_cb( 0, RETRO_DEVICE_JOYPAD, 0, id )) p |= 1u << id;
	lr_pad = p;
}

typedef void (*disp_frame_fn)( const void *pixels, int w, int h, int pitch );
static disp_frame_fn direct_fn;
static int direct_state = -1;      // -1 not tried, 0 off, 1 on

// Direct present: picoarch's video callback pre-scales the frame in software and copies it twice (8-9 ms per
// frame on the device). The display driver it loaded (cubegm/driver*.so) takes any frame size
// and lets the hardware scale it: video_driver_disp_frame( pixels, w, h, pitch ) copies the rows once and wakes
// its display thread. The core calls it itself and gives picoarch a NULL (repeat) frame, which costs nothing.
// Only a driver picoarch already loaded is used (RTLD_NOLOAD); without one, or with <port dir>/direct_off.txt,
// frames go through video_cb as before.
static int direct_frames;          // frames shown through picoarch first, so its driver is set up

static void direct_init( void )
{
	direct_state = 0;
	char off[600]; struct stat st;
	snprintf( off, sizeof off, "%s/direct_off.txt", base_dir );
	if( stat( off, &st ) == 0 ) return;
	static const char *names[] = { "/mnt/sdcard/cubegm/driver.so", "/mnt/sdcard/cubegm/driver_r36sx.so",
		"/mnt/sdcard/cubegm/driver_r36sx27.so", "/mnt/sdcard/cubegm/driver_sf3000.so",
		"/mnt/sdcard/cubegm/driver_sf3500.so", "/mnt/sdcard/cubegm/driver_gb350.so" };
	direct_fn = (disp_frame_fn)dlsym( RTLD_DEFAULT, "video_driver_disp_frame" );
	for( unsigned i = 0; !direct_fn && i < sizeof names / sizeof names[0]; i++ )
	{
		void *h = dlopen( names[i], RTLD_NOW | RTLD_NOLOAD );
		if( h ) direct_fn = (disp_frame_fn)dlsym( h, "video_driver_disp_frame" );
	}
	direct_state = direct_fn ? 1 : 0;
	fprintf( stderr, "[hl] direct present: %s\n", direct_fn ? "on" : "off (no display driver loaded)" );
}

// Big FPS counter in the top-left corner (picoarch's own overlay is not drawn when frames bypass it).
// Core option hl_fps_overlay: on|off. Digits are a 5x7 font scaled to about 1/9 of the frame height.
static const uint8_t font5x7[][7] = {
	{ 14, 17, 19, 21, 25, 17, 14 }, { 4, 12, 4, 4, 4, 4, 14 }, { 14, 17, 1, 2, 4, 8, 31 }, { 31, 2, 4, 2, 1, 17, 14 },
	{ 2, 6, 10, 18, 31, 2, 2 }, { 31, 16, 30, 1, 1, 17, 14 }, { 6, 8, 16, 30, 17, 17, 14 }, { 31, 1, 2, 4, 8, 8, 8 },
	{ 14, 17, 17, 14, 17, 17, 14 }, { 14, 17, 17, 15, 1, 2, 12 },
	{ 31, 16, 16, 30, 16, 16, 16 },   // F (10)
	{ 30, 17, 17, 30, 16, 16, 16 },   // P (11)
	{ 15, 16, 16, 14, 1, 1, 30 },     // S (12)
};
static int fps_overlay = -1;
static void draw_fps( uint16_t *px, int w, int h )
{
	static double t0; static int n, shown;
	double t = now_s( );
	if( t0 == 0 ) t0 = t;
	n++;
	if( t - t0 >= 0.5 ) { shown = (int)( n / ( t - t0 ) + 0.5 ); n = 0; t0 = t; }
	int glyph[6], ng = 0;
	glyph[ng++] = 10; glyph[ng++] = 11; glyph[ng++] = 12; glyph[ng++] = -1;
	int v = shown > 999 ? 999 : shown;
	if( v >= 100 ) glyph[ng++] = v / 100;
	if( v >= 10 ) glyph[ng++] = ( v / 10 ) % 10;
	if( ng < 6 ) glyph[ng++] = v % 10;
	int s = h / 96; if( s < 2 ) s = 2;          // 256x192 -> 2, 640x480 -> 5
	int bw = ( ng * 6 + 1 ) * s, bh = 9 * s;
	if( bw > w ) bw = w;
	uint16_t col = shown >= 30 ? 0x07E0 : shown >= 20 ? 0xFFE0 : 0xF800;   // green, yellow, red
	for( int y = 0; y < bh && y < h; y++ ) for( int x = 0; x < bw; x++ ) px[y * w + x] = 0;
	for( int g = 0; g < ng; g++ )
	{
		if( glyph[g] < 0 ) continue;
		const uint8_t *rows = font5x7[glyph[g]];
		for( int r = 0; r < 7; r++ ) for( int c = 0; c < 5; c++ )
		{
			if( !( rows[r] & ( 16 >> c ))) continue;
			int x0 = ( 1 + g * 6 + c ) * s, y0 = ( 1 + r ) * s;
			for( int yy = 0; yy < s; yy++ ) for( int xx = 0; xx < s; xx++ )
				if( x0 + xx < w && y0 + yy < h ) px[( y0 + yy ) * w + x0 + xx] = col;
		}
	}
}

// returns 1 when the frame was shown without picoarch
static int direct_present( const uint16_t *f, int w, int h )
{
	if( direct_state < 0 ) direct_init( );
	if( direct_state <= 0 ) return 0;
	if( direct_frames < 30 ) { direct_frames++; return 0; }
	direct_fn( f, w, h, w * 2 );
	return 1;
}

void retro_run( void )
{
	static double last_audio;
	static int16_t pcm[2 * 4096];
	static int shown_w = 256, shown_h = 192;

	// 1. run one engine loop (lock step)
	read_pad( );
	if( !game_ended ) sem_post( &sem_go );
	while( sem_wait( &sem_done ) != 0 && errno == EINTR ) { }
	if( game_ended )
	{
		env_cb( RETRO_ENVIRONMENT_SHUTDOWN, NULL );
		video_cb( black, 256, 192, 256 * 2 );
		return;
	}

	// 2. the engine is stopped: take its frame and its sound
	const uint16_t *f = fresh_frame;
	int fw = frame_w, fh = frame_h;
	fresh_frame = NULL;
	double t = now_s( );
	if( last_audio == 0 ) last_audio = t - 1.0 / CORE_FPS;
	int n = (int)(( t - last_audio ) * AUDIO_RATE);   // sound for the real time since the last call (bounded)
	if( n > 4096 ) { n = 4096; last_audio = t; }
	else last_audio += (double)n / AUDIO_RATE;
	if( n > 0 ) LR_SoundPull( pcm, n );

	// 3. present and play
	if( f )
	{
		if( fw != shown_w || fh != shown_h )
		{	// menus switch between the game size and 640x480: tell the frontend
			struct retro_game_geometry g = { (unsigned)fw, (unsigned)fh, 640, 480, 4.0f / 3.0f };
			env_cb( RETRO_ENVIRONMENT_SET_GEOMETRY, &g );
			shown_w = fw; shown_h = fh;
		}
		if( fps_overlay < 0 ) { const char *o = core_option( "hl_fps_overlay" ); fps_overlay = !o || strcmp( o, "off" ); }
		if( fps_overlay ) draw_fps( (uint16_t *)f, fw, fh );
		if( direct_present( f, fw, fh )) video_cb( NULL, fw, fh, fw * 2 );
		else video_cb( f, fw, fh, fw * 2 );
		last_frame = f;
	}
	else if( last_frame ) video_cb( NULL, shown_w, shown_h, shown_w * 2 );
	else video_cb( black, 256, 192, 256 * 2 );
	if( n > 0 && audio_cb ) audio_cb( pcm, n );
}
