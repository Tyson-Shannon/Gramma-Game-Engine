#include "pc_internal.h"
#include <stddef.h>

/*
 * A deliberately small software renderer. It draws the exact tile data the
 * asset pipeline emits, so the simulator exercises the same arrays that
 * console backends consume. Output is RGB565 for a streaming SDL texture.
 */

uint16_t pc_rgb565(gr_color color)
{
    uint16_t r = (uint16_t)((color >> 10) & 0x1fu);
    uint16_t g = (uint16_t)((color >> 5) & 0x1fu);
    uint16_t b = (uint16_t)(color & 0x1fu);
    return (uint16_t)((r << 11) | (((g << 1) | (g >> 4)) << 6) | b);
}

void pc_clear(uint16_t *fb, int width, int height, gr_color color)
{
    int i;
    uint16_t value = pc_rgb565(color);
    for (i = 0; i < width * height; ++i) {
        fb[i] = value;
    }
}

static uint8_t tile_pixel(const gr_tileset *ts, uint16_t tile, int x, int y)
{
    int row_bytes = (ts->bpp == 0) ? 1 : (8 * ts->bpp / 8);
    const uint8_t *row;

    if (tile >= ts->tile_count || x < 0 || x > 7 || y < 0 || y > 7) {
        return 0;
    }
    row = ts->tiles + (size_t)tile * (size_t)(8 * row_bytes) +
          (size_t)y * (size_t)row_bytes;

    if (ts->bpp >= 8) {
        return row[x];
    }
    {
        int per_byte = 8 / ts->bpp;
        int shift = 8 - ts->bpp - (x % per_byte) * ts->bpp;
        return (uint8_t)((row[x / per_byte] >> shift) &
                         ((1u << ts->bpp) - 1u));
    }
}

static const gr_color *resolve_palette(const gr_tileset *ts, uint8_t slot,
                                       const gr_color (*palettes)[GR_PALETTE_COLORS],
                                       const bool *palette_used)
{
    if (palette_used != NULL && slot < GR_MAX_PALETTES && palette_used[slot]) {
        return palettes[slot];
    }
    return ts != NULL ? ts->palette : NULL;
}

static void draw_tile(uint16_t *fb, int fb_w, int fb_h,
                      const gr_tileset *ts, uint16_t tile,
                      int dx, int dy, const gr_color *palette,
                      uint8_t flip)
{
    int x, y;

    if (ts == NULL || ts->tiles == NULL || palette == NULL) {
        return;
    }
    for (y = 0; y < 8; ++y) {
        for (x = 0; x < 8; ++x) {
            int sx = (flip & GR_FLIP_X) ? 7 - x : x;
            int sy = (flip & GR_FLIP_Y) ? 7 - y : y;
            uint8_t index = tile_pixel(ts, tile, sx, sy);
            int px = dx + x;
            int py = dy + y;
            if (index == 0 || px < 0 || py < 0 || px >= fb_w || py >= fb_h) {
                continue;
            }
            if (index < ts->palette_size) {
                fb[py * fb_w + px] = pc_rgb565(palette[index]);
            }
        }
    }
}

static int floor_div(int a, int b)
{
    int q = a / b;
    if ((a % b) != 0 && ((a < 0) != (b < 0))) {
        --q;
    }
    return q;
}

static int wrap(int value, int modulus)
{
    int r = value % modulus;
    return r < 0 ? r + modulus : r;
}

void pc_draw_bg(uint16_t *fb, int width, int height, const gr_bg *bg,
                const gr_color (*palettes)[GR_PALETTE_COLORS],
                const bool *palette_used)
{
    const gr_color *palette;
    int origin_x, origin_y, offset_x, offset_y;
    int ty, tx;

    if (bg == NULL || bg->tileset == NULL || bg->map == NULL ||
        bg->map->width == 0 || bg->map->height == 0 ||
        bg->map->tiles == NULL) {
        return;
    }
    palette = resolve_palette(bg->tileset, bg->pal_slot, palettes, palette_used);
    if (palette == NULL) {
        return;
    }
    origin_x = floor_div(bg->scroll_x, 8);
    origin_y = floor_div(bg->scroll_y, 8);
    offset_x = bg->scroll_x - origin_x * 8;
    offset_y = bg->scroll_y - origin_y * 8;

    for (ty = 0; ty < height; ty += 8) {
        for (tx = 0; tx < width; tx += 8) {
            int mx = wrap(origin_x + tx / 8, bg->map->width);
            int my = wrap(origin_y + ty / 8, bg->map->height);
            uint16_t tile = bg->map->tiles[my * bg->map->width + mx];
            draw_tile(fb, width, height, bg->tileset, tile,
                      tx - offset_x, ty - offset_y, palette, 0);
        }
    }
}

void pc_draw_sprite(uint16_t *fb, int width, int height,
                    const gr_sprite *sprite,
                    const gr_color (*palettes)[GR_PALETTE_COLORS],
                    const bool *palette_used)
{
    const gr_color *palette;
    uint8_t fw, fh;
    uint16_t first;
    int ty, tx;
    uint8_t frame;

    if (sprite == NULL || !sprite->visible || sprite->tileset == NULL) {
        return;
    }
    palette = resolve_palette(sprite->tileset, sprite->pal_slot,
                              palettes, palette_used);
    if (palette == NULL) {
        return;
    }
    fw = sprite->frame_w ? sprite->frame_w : 1;
    fh = sprite->frame_h ? sprite->frame_h : 1;
    frame = sprite->frame;
    first = (uint16_t)((uint16_t)frame * fw * fh);

    for (ty = 0; ty < fh; ++ty) {
        for (tx = 0; tx < fw; ++tx) {
            uint16_t tile = (uint16_t)(first + ty * fw + tx);
            draw_tile(fb, width, height, sprite->tileset, tile,
                      sprite->x + tx * 8, sprite->y + ty * 8,
                      palette, sprite->flip);
        }
    }
}
