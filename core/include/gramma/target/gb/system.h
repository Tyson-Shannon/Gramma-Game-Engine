#ifndef GRAMMA_GB_SYSTEM_H
#define GRAMMA_GB_SYSTEM_H

/*
 * Opt-in Game Boy system information. Include this header only in GB builds or
 * in portable code prepared to handle GR_ERR_UNSUPPORTED. It is not part of
 * gramma.h and does not add a runtime dependency to the base API.
 */

#include <gramma/types.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GR_GB_TILE_BYTES      16u
#define GR_GB_TILE_BPP        2u
#define GR_GB_PALETTE_COLORS  4u
#define GR_GB_PALETTE_SLOTS   8u
#define GR_GB_PLAYERS         1u
#define GR_GB_SCREEN_W        160u
#define GR_GB_SCREEN_H        144u

typedef struct {
    uint8_t     tile_bytes;      /* 16 for a native 2bpp CHR tile */
    uint8_t     bpp;
    uint8_t     palette_colors;
    uint8_t     palette_slots;
    uint8_t     players;
    uint16_t    screen_w;
    uint16_t    screen_h;
    const char *name;
} gr_gb_system_caps;

/* Fill *out with GB capabilities. Returns GR_ERR_UNSUPPORTED on other targets. */
gr_result gr_gb_system_query(gr_gb_system_caps *out);

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_GB_SYSTEM_H */
