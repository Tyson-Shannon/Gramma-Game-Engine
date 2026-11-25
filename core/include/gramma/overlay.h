#ifndef GRAMMA_OVERLAY_H
#define GRAMMA_OVERLAY_H

/*
 * Opt-in vblank overlay queue. Games stage small tile or nametable changes
 * here; each backend applies them during its vblank window instead of writing
 * video memory from game code. Banked source data must be selected by the
 * caller before staging it, because the bytes are copied immediately.
 */

#include <gramma/types.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Bounds keep the queue small enough for 8-bit work RAM. */
#define GR_OVERLAY_MAX_OPS       8u
#define GR_OVERLAY_TILE_BYTES    256u   /* 16 tiles at 16 bytes each */
#define GR_OVERLAY_MAP_BYTES     64u    /* one 8x8 nametable patch */

/* Stage `bytes` of tile data into VRAM tile `dest`. The byte format is the
 * native tile format of the target: GB/NES use 16 bytes per tile, SMS uses 32. */
gr_result gr_overlay_tiles(uint8_t dest, const uint8_t *src, uint16_t bytes,
                           bool sprite);

/* Stage a rectangular patch of 8x8 tile indices at (x, y). Coordinates are in
 * tiles and use the target's nametable origin. */
gr_result gr_overlay_nametable(uint8_t x, uint8_t y, uint8_t w, uint8_t h,
                               const uint8_t *tiles);

/* Apply and clear queued operations. Backends call this from their vblank
 * handler; games normally do not need to call it. */
gr_result gr_overlay_flush(void);
void      gr_overlay_clear(void);
uint8_t   gr_overlay_pending(void);

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_OVERLAY_H */
