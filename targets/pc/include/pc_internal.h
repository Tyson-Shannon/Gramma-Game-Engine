#ifndef GRAMMA_PC_INTERNAL_H
#define GRAMMA_PC_INTERNAL_H

#include <gramma/gramma.h>

/* Software rasterizer and audio synthesizer shared by the PC backend. */

uint16_t pc_rgb565(gr_color color);

void pc_clear(uint16_t *fb, int width, int height, gr_color color);
void pc_draw_bg(uint16_t *fb, int width, int height, const gr_bg *bg,
                const gr_color (*palettes)[GR_PALETTE_COLORS],
                const bool *palette_used);
void pc_draw_sprite(uint16_t *fb, int width, int height,
                    const gr_sprite *sprite,
                    const gr_color (*palettes)[GR_PALETTE_COLORS],
                    const bool *palette_used);

bool pc_audio_init(const gr_config *cfg);
void pc_audio_quit(void);
void pc_audio_tick(uint32_t dt_ms);

/* Wrappers implementing the portable backend's audio operations. */
gr_result pc_backend_music_play(const gr_song *song);
void pc_backend_music_stop(void);
void pc_backend_sfx_play(uint16_t id, uint8_t channel);

#endif /* GRAMMA_PC_INTERNAL_H */
