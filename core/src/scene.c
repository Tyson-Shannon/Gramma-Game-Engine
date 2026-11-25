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
}
