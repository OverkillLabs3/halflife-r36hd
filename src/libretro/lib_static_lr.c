/*
lib_static_lr.c - static library table for the libretro core (replaces engine/platform/misc/lib_static.c).
Same lookups; HL_LIBDEBUG=1 prints every library and symbol request.
*/
#include "platform/platform.h"
#include "library.h"

#if XASH_LIB == LIB_STATIC
typedef struct table_s
{
	const char *name;
	void *pointer;
} table_t;

#include "generated_library_tables.h"

static int lib_debug = -1;
static void *Lib_Find( table_t *tbl, const char *name )
{
	if( lib_debug < 0 ) lib_debug = getenv( "HL_LIBDEBUG" ) ? 1 : 0;
	if( !tbl ) return NULL;
	while( tbl->name )
	{
		if( !Q_strcmp( tbl->name, name ))
			return tbl->pointer;
		tbl++;
	}
	if( lib_debug ) fprintf( stderr, "[lib] not found: %s\n", name );
	return 0;
}

void *COM_LoadLibrary( const char *dllname, int build_ordinals_table, qboolean directpath )
{
	void *p = Lib_Find( (table_t *)libs, dllname );
	if( lib_debug ) fprintf( stderr, "[lib] load %s -> %p\n", dllname, p );
	return p;
}

void COM_FreeLibrary( void *hInstance ) { }

void *COM_GetProcAddress( void *hInstance, const char *name )
{
	return Lib_Find( hInstance, name );
}

void *COM_GetProcAddressFromDependency( void *hInstance, const char *depname, const char *name )
{
	return NULL;
}

void *COM_FunctionFromName( void *hInstance, const char *pName )
{
	return Lib_Find( hInstance, pName );
}

const char *COM_NameForFunction( void *hInstance, void *function )
{
#ifdef XASH_ALLOW_SAVERESTORE_OFFSETS
	return COM_OffsetNameForFunction( function );
#else
	return NULL;
#endif
}
#endif
