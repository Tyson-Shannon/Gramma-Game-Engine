#ifndef GRAMMA_SMS_SYSTEM_H
#define GRAMMA_SMS_SYSTEM_H

/*
 * Opt-in Master System / Game Gear information. The VDP uses 4bpp planar
 * tiles: 32 bytes per 8x8 tile, 16 CRAM colours per palette and sprite tiles
 * start at VRAM tile 256. The console build flag TARGET_GG is not needed to
 * query capabilities; both systems share these values.
 */

#include <gramma/types.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GR_SMS_TILE_BYTES        32u
#define GR_SMS_TILE_BPP          4u
#define GR_SMS_PALETTE_COLORS    16u
#define GR_SMS_PALETTE_SLOTS     2u
#define GR_SMS_PLAYERS           2u
#define GR_SMS_SCREEN_W          256u
#define GR_SMS_SCREEN_H          192u
#define GR_SMS_SPRITE_TILE_BASE  256u

typedef struct {
    uint8_t     tile_bytes;
    uint8_t     bpp;
    uint8_t     palette_colors;
    uint8_t     palette_slots;
    uint8_t     players;
    uint16_t    screen_w;
    uint16_t    screen_h;
    uint16_t    sprite_tile_base;
    const char *name;
} gr_sms_system_caps;

/* Fill *out with SMS/GG capabilities. Returns GR_ERR_UNSUPPORTED elsewhere. */
gr_result gr_sms_system_query(gr_sms_system_caps *out);

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_SMS_SYSTEM_H */
