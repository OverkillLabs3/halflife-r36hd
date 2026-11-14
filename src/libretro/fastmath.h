/* fastmath.h - forced into every Half-Life source (-include). floorf/ceilf are library calls on this
   toolchain (~50 instructions each and the most called libm functions in the game); these give the same
   result for every float: values of 2^23 and more are already whole numbers, NaN passes through. */
#ifndef HL_FASTMATH_H
#define HL_FASTMATH_H
#ifdef __cplusplus
#include <cmath>
#else
#include <math.h>
#endif
static inline float hl_floorf( float x )
{
	if( !( x > -8388608.0f && x < 8388608.0f )) return x;
	float r = (float)(int)x;
	return r > x ? r - 1.0f : r;
}
static inline float hl_ceilf( float x )
{
	if( !( x > -8388608.0f && x < 8388608.0f )) return x;
	float r = (float)(int)x;
	return r < x ? r + 1.0f : r;
}
#ifndef __cplusplus
#define floorf( x ) hl_floorf( x )
#define ceilf( x ) hl_ceilf( x )
#endif
#endif
