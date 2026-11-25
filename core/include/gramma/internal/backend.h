#ifndef GRAMMA_INTERNAL_BACKEND_H
#define GRAMMA_INTERNAL_BACKEND_H

/* Internal contract between the portable core and each console backend. */

#include <gramma/types.h>

typedef struct {
    const char *id;
    uint16_t    supported_buttons[GR_PLAYER_COUNT];

    gr_result (*init)(const gr_config *cfg);
    void      (*quit)(void);

    void (*frame_begin)(void);
    void (*frame_draw)(const gr_bg *bg,
                       gr_actor *const *actors, uint8_t actor_count);
    void (*frame_end)(void);

    bool     (*pad_down)(gr_player player, gr_button button);
    bool     (*pad_pressed)(gr_player player, gr_button button);
    bool     (*pad_released)(gr_player player, gr_button button);
    void     (*palette_load)(uint8_t slot, const gr_color *colors, uint8_t count);

    gr_result (*music_play)(const gr_song *song);
    void      (*music_stop)(void);
    void      (*sfx_play)(uint16_t id, uint8_t channel);

    uint32_t (*ticks)(void);
    bool     (*quit_requested)(void);

    /* Vblank overlay hooks used by the opt-in gramma/overlay.h queue. */
    gr_result (*overlay_tiles)(uint8_t dest, const uint8_t *data,
                               uint16_t count, bool sprite);
    gr_result (*overlay_nametable)(uint8_t x, uint8_t y, uint8_t w, uint8_t h,
                                   const uint8_t *tiles);
} gr_backend;

const gr_backend *gr_backend_get(void);
void gr_draw_frame(void);

#endif /* GRAMMA_INTERNAL_BACKEND_H */
