#ifndef GRAMMA_NES_SYSTEM_H
#define GRAMMA_NES_SYSTEM_H

/*
 * Opt-in NES system information. Values describe the stock 2C02 PPU: one
 * nametable, 8x8 2bpp background/sprite tiles and two serial controllers.
 * Mapper banks remain in the separate target/nes/mapper.h extension.
 */

#include <gramma/types.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GR_NES_TILE_BYTES      16u
#define GR_NES_TILE_BPP        2u
#define GR_NES_PALETTE_COLORS  4u
#define GR_NES_PALETTE_SLOTS   8u
#define GR_NES_PLAYERS         2u
#define GR_NES_SCREEN_W        256u
#define GR_NES_SCREEN_H        240u
#define GR_NES_NAMETABLE_W     32u
#define GR_NES_NAMETABLE_H     30u

typedef struct {
    uint8_t     tile_bytes;
    uint8_t     bpp;
    uint8_t     palette_colors;
    uint8_t     palette_slots;
    uint8_t     players;
    uint16_t    screen_w;
    uint16_t    screen_h;
    uint8_t     nametable_w;
    uint8_t     nametable_h;
    const char *name;
} gr_nes_system_caps;

/* Fill *out with NES capabilities. Returns GR_ERR_UNSUPPORTED elsewhere. */
gr_result gr_nes_system_query(gr_nes_system_caps *out);

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_NES_SYSTEM_H */
