#ifndef GRAMMA_H
#define GRAMMA_H

#include <gramma/types.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Lifecycle ------------------------------------------------------------- */

gr_result gr_init(const gr_config *cfg);
void      gr_quit(void);
/* Runs game_init, then a 60 Hz fixed-step loop until quit is requested. */
int       gr_run(void);

void gr_begin_frame(void);
void gr_end_frame(void);
bool gr_quit_requested(void);
void gr_request_quit(void);
uint32_t gr_ticks(void);

/* Scenes and actors ----------------------------------------------------- */

gr_result gr_scene_load(gr_scene *scene);
gr_scene *gr_scene_current(void);
void      gr_actor_clear(void);
gr_actor *gr_actor_spawn(const gr_actor_def *def);
void      gr_actor_destroy(gr_actor *actor);
uint8_t   gr_actor_count(void);
void      gr_actor_update_all(gr_fixed dt);

/* Sprites and backgrounds ----------------------------------------------- */

gr_result gr_palette_load(uint8_t slot, const gr_color *colors, uint8_t count);
void gr_bg_init(gr_bg *bg, const gr_tileset *tileset, const gr_map *map,
                uint8_t pal_slot);
void gr_bg_set_scroll(gr_bg *bg, int16_t x, int16_t y);
/* Select one of four PPU nametables (NES; ignored elsewhere). */
void gr_bg_set_nametable(gr_bg *bg, uint8_t nametable);
/* Per-tile background palette indices (0..3), or NULL for one flat palette.
 * The array must have at least map->width * map->height bytes and stay valid
 * while the background is drawn. */
void gr_bg_set_palette_map(gr_bg *bg, const uint8_t *palette_map);
/* Pack the four 16x16 regions inside one attribute block (ax, ay) into the
 * 2-bits-per-region byte used by tile hardware. Portable so it can be tested
 * on the host and shared by backends. */
uint8_t gr_bg_attribute(const gr_bg *bg, uint8_t ax, uint8_t ay);
void gr_sprite_show(gr_sprite *s, uint8_t pal_slot, int16_t x, int16_t y);
void gr_sprite_hide(gr_sprite *s);
void gr_sprite_set_frame(gr_sprite *s, uint8_t frame);
void gr_sprite_set_flip(gr_sprite *s, bool x, bool y);

/* Input ----------------------------------------------------------------- */

bool gr_pad_down(gr_player player, gr_button button);
bool gr_pad_pressed(gr_player player, gr_button button);
bool gr_pad_released(gr_player player, gr_button button);

/* Audio ----------------------------------------------------------------- */

gr_result gr_music_play(const gr_song *song);
void      gr_music_stop(void);
void      gr_sfx_play(uint16_t sfx_id, uint8_t channel);

#ifdef __cplusplus
}
#endif

#endif /* GRAMMA_H */
