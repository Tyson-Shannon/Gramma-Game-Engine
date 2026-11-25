#include <gramma/gramma.h>

/* Scenes are plain structs: the core owns only a pointer to the active one.
   Keeping helpers here gives C games and transpiled Grain the same surface. */

void gr_bg_init(gr_bg *bg, const gr_tileset *tileset, const gr_map *map,
                uint8_t pal_slot)
{
    if (bg == NULL) {
        return;
    }
    bg->tileset = tileset;
    bg->map = map;
    bg->pal_slot = pal_slot;
    bg->scroll_x = 0;
    bg->scroll_y = 0;
    bg->visible = true;
    bg->nametable = 0u;
    bg->palette_map = NULL;
}

void gr_bg_set_nametable(gr_bg *bg, uint8_t nametable)
{
    if (bg != NULL) {
        bg->nametable = (uint8_t)(nametable & 3u);
    }
}

void gr_bg_set_palette_map(gr_bg *bg, const uint8_t *palette_map)
{
    if (bg != NULL) {
        bg->palette_map = palette_map;
    }
}

uint8_t gr_bg_attribute(const gr_bg *bg, uint8_t ax, uint8_t ay)
{
    uint8_t rx, ry;
    uint8_t attr;

    if (bg == NULL || bg->map == NULL || ax >= 8u || ay >= 8u) {
        return 0u;
    }
    if (bg->palette_map == NULL || bg->map->width == 0u ||
        bg->map->height == 0u) {
        return (uint8_t)((bg->pal_slot & 3u) * 0x55u);
    }
    attr = 0u;
    for (ry = 0u; ry < 2u; ++ry) {
        for (rx = 0u; rx < 2u; ++rx) {
            uint16_t mx = (uint16_t)(ax * 4u + rx * 2u);
            uint16_t my = (uint16_t)(ay * 4u + ry * 2u);
            uint8_t slot = 0u;
            if (mx < bg->map->width && my < bg->map->height) {
                uint16_t index = (uint16_t)(my * bg->map->width + mx);
                slot = (uint8_t)(bg->palette_map[index] & 3u);
            }
            attr = (uint8_t)(attr | (uint8_t)(slot << ((ry * 2u + rx) * 2u)));
        }
    }
    return attr;
}
