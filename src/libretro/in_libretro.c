/*
in_libretro.c - R36HD pad for Half-Life. Uses the evdev backend slot (XASH_USE_EVDEV) of the engine.
The device has a D-pad, A/B/X/Y (the right stick is wired to them), L1/L2/R1/R2, SELECT, START, and no analog values.

In game:  D-pad move/strafe, A/B/X/Y look (accelerating), R1 fire, L1 jump, SELECT+L1 alt fire,
          R2 use, L2 duck, SELECT+Up/Down previous/next weapon, SELECT+Left reload, SELECT+Right flashlight,
          START menu.
In menus: D-pad arrows, A enter, B or START back.
The keys are bound in valve/userconfig.d/r36hd.cfg (written by the core at start).
*/
#include "platform/platform.h"
#if XASH_USE_EVDEV
#include "input.h"
#include "client.h"
#include "keydefs.h"
#include "hl_libretro.h"

volatile uint32_t lr_pad;

// libretro joypad ids
enum { J_B = 0, J_Y = 1, J_SELECT = 2, J_START = 3, J_UP = 4, J_DOWN = 5, J_LEFT = 6, J_RIGHT = 7,
       J_A = 8, J_X = 9, J_L = 10, J_R = 11, J_L2 = 12, J_R2 = 13, J_COUNT = 16 };

static uint32_t prev_pad;
static int held_key[J_COUNT];      // engine key sent for a pressed button (0 = none)
static double hold_start[4];       // look buttons: when they went down

void Evdev_SetGrab( qboolean grab ) { }
void Platform_EnableTextInput( qboolean enable, int x, int y, int w, int h ) { }
void Evdev_Shutdown( void ) { }
void Evdev_Init( void ) { }

static int map_button( int b, qboolean menu, qboolean sel )
{
	if( menu )
	{
		switch( b )
		{
		case J_UP: return K_UPARROW;
		case J_DOWN: return K_DOWNARROW;
		case J_LEFT: return K_LEFTARROW;
		case J_RIGHT: return K_RIGHTARROW;
		case J_A: return K_ENTER;
		case J_B: return K_ESCAPE;
		case J_START: return K_ESCAPE;
		case J_X: return K_BACKSPACE;
		case J_Y: return K_TAB;
		case J_L: return K_PGUP;
		case J_R: return K_PGDN;
		default: return 0;
		}
	}
	if( sel )
	{
		switch( b )
		{
		case J_UP: return K_MWHEELUP;      // invprev
		case J_DOWN: return K_MWHEELDOWN;  // invnext
		case J_LEFT: return 'r';           // +reload
		case J_RIGHT: return 'f';          // flashlight
		case J_L: return K_MOUSE2;         // +attack2
		case J_X: return K_F6;             // quick save
		case J_Y: return K_F9;             // quick load
		case J_A: return 'n';              // night vision / unused, kept free
		default: break;
		}
	}
	switch( b )
	{
	case J_UP: return K_UPARROW;           // +forward
	case J_DOWN: return K_DOWNARROW;       // +back
	case J_LEFT: return K_LEFTARROW;       // +moveleft
	case J_RIGHT: return K_RIGHTARROW;     // +moveright
	case J_R: return K_MOUSE1;             // +attack
	case J_L: return K_SPACE;              // +jump
	case J_R2: return 'e';                 // +use
	case J_L2: return K_CTRL;              // +duck
	case J_START: return K_ESCAPE;         // menu
	default: return 0;                     // A/B/X/Y look, SELECT is a modifier
	}
}

void IN_EvdevFrame( void )
{
	uint32_t pad = lr_pad;
	uint32_t changed = pad ^ prev_pad;
	qboolean menu = cls.key_dest != key_game;
	qboolean sel = ( pad & ( 1u << J_SELECT )) != 0;

	for( int b = 0; b < J_COUNT && changed; b++ )
	{
		uint32_t bit = 1u << b;
		if( !( changed & bit ))
			continue;
		if( pad & bit )
		{
			int k = map_button( b, menu, sel );
			if( k )
			{
				held_key[b] = k;
				Key_Event( k, true );
				if( k == K_MWHEELUP || k == K_MWHEELDOWN ) // wheel keys are a press and release
				{
					Key_Event( k, false );
					held_key[b] = 0;
				}
			}
			if( b == J_Y ) hold_start[0] = host.realtime;
			if( b == J_A ) hold_start[1] = host.realtime;
			if( b == J_X ) hold_start[2] = host.realtime;
			if( b == J_B ) hold_start[3] = host.realtime;
		}
		else if( held_key[b] )
		{
			Key_Event( held_key[b], false );
			held_key[b] = 0;
		}
	}
	prev_pad = pad;
}

// look speed in degrees per second: starts slow for aiming and speeds up while held
static float look_speed( int i, float base, float top )
{
	float t = (float)( host.realtime - hold_start[i] );
	float s = base + t * 360.0f;
	return s > top ? top : s;
}

void IN_EvdevMove( float *yaw, float *pitch )
{
	if( cls.key_dest != key_game )
		return;
	uint32_t pad = lr_pad;
	float dt = host.realframetime;
	if( pad & ( 1u << J_SELECT )) return;   // SELECT + face buttons are commands, not looking
	if( pad & ( 1u << J_Y )) *yaw   += look_speed( 0, 70.0f, 220.0f ) * dt;
	if( pad & ( 1u << J_A )) *yaw   -= look_speed( 1, 70.0f, 220.0f ) * dt;
	if( pad & ( 1u << J_X )) *pitch -= look_speed( 2, 50.0f, 150.0f ) * dt;
	if( pad & ( 1u << J_B )) *pitch += look_speed( 3, 50.0f, 150.0f ) * dt;
}

#endif
