/*
s_libretro.c - sound output for the libretro core. The engine mixes into a ring buffer ahead of the play
position; retro_run takes the samples for the real time that passed and moves the play position on.
Replaces engine/platform/linux/s_alsa.c (same backend slot, XASH_SOUND == SOUND_ALSA).
*/
#include "platform/platform.h"
#if XASH_SOUND == SOUND_ALSA
#include "sound.h"
#include "hl_libretro.h"

#define LR_SND_SAMPLES 16384   // 8192 stereo frames, 0.37 s at 22050 Hz

static qboolean lr_paused;

qboolean SNDDMA_Init( void )
{
	snd.format.speed = SOUND_DMA_SPEED;
	snd.format.channels = 2;
	snd.format.width = 2;
	snd.samples = LR_SND_SAMPLES;
	snd.samplepos = 0;
	snd.buffer = Mem_Calloc( sndpool, LR_SND_SAMPLES * 2 );
	snd.initialized = 1;
	snd.backend_name = "libretro";
	return true;
}

void SNDDMA_Shutdown( void )
{
	snd.initialized = false;
	if( snd.buffer )
	{
		Mem_Free( snd.buffer );
		snd.buffer = NULL;
	}
}

void SNDDMA_Submit( void ) { }
void SNDDMA_BeginPainting( void ) { }
void SNDDMA_Activate( qboolean active ) { lr_paused = !active; }

// called by the core between engine frames: copy 'frames' stereo frames from the play position
int LR_SoundPull( int16_t *out, int frames )
{
	if( !snd.initialized || !snd.buffer || lr_paused )
	{
		memset( out, 0, frames * 4 );
		return frames;
	}
	int16_t *ring = (int16_t *)snd.buffer;
	int pos = snd.samplepos;              // in samples (two per frame)
	for( int i = 0; i < frames * 2; i++ )
	{
		out[i] = ring[pos];
		ring[pos] = 0;                    // if the engine falls behind, play silence, not the old loop
		pos++;
		if( pos >= snd.samples ) pos = 0;
	}
	snd.samplepos = pos;
	return frames;
}

qboolean VoiceCapture_Init( void ) { return false; }
qboolean VoiceCapture_Activate( qboolean activate ) { return false; }
qboolean VoiceCapture_Lock( qboolean lock ) { return false; }
void VoiceCapture_Shutdown( void ) { }

#endif
