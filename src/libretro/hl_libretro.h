// Glue between the Xash3D platform layer (vid/s/in_libretro.c, inside the engine) and the libretro core (hl_core.c).
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// core -> engine
void LR_SetVideoSize( int w, int h );
int LR_SoundPull( int16_t *out, int frames );

// engine -> core
void LR_FrameReady( const uint16_t *pixels, int w, int h );   // a frame is finished (SW_UnlockBuffer)
void LR_Sync( void );                                          // once per engine main-loop iteration

// pad state, written by the core between engine frames (libretro joypad id bits), read by in_libretro.c
extern volatile uint32_t lr_pad;

#ifdef __cplusplus
}
#endif
