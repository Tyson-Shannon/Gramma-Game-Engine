#include <gramma/gramma.h>
#include <gramma/internal/actor_list.h>
#include <gramma/internal/backend.h>

/* Portable core: owns lifecycle, the frame loop and dispatch to a backend. */

static const gr_config *g_cfg;
static const gr_backend *g_backend;
static gr_scene *g_scene;
static bool g_initialized;
static bool g_quit;
static bool g_in_frame;

#if defined(GRAMMA_TARGET_PC)
extern const gr_backend gr_backend_pc;
#endif
#if defined(GRAMMA_TARGET_GB)
extern const gr_backend gr_backend_gb;
#endif
#if defined(GRAMMA_TARGET_NES)
extern const gr_backend gr_backend_nes;
#endif
#if defined(GRAMMA_TARGET_SMS)
extern const gr_backend gr_backend_sms;
#endif

static const gr_backend *select_backend(void)
{
#if defined(GRAMMA_TARGET_PC)
    return &gr_backend_pc;
#elif defined(GRAMMA_TARGET_GB)
    return &gr_backend_gb;
#elif defined(GRAMMA_TARGET_NES)
    return &gr_backend_nes;
#elif defined(GRAMMA_TARGET_SMS)
    return &gr_backend_sms;
#else
    return NULL;
#endif
}

gr_result gr_init(const gr_config *cfg)
{
    gr_result result;
    uint8_t p, b;

    if (cfg == NULL || g_initialized) {
        return GR_ERR_INVALID_ARG;
    }
    g_backend = select_backend();
    if (g_backend == NULL) {
        return GR_ERR_UNSUPPORTED;
    }
    if (cfg->width == 0 || cfg->height == 0 ||
        (cfg->width % 8u) != 0 || (cfg->height % 8u) != 0) {
        return GR_ERR_INVALID_ARG;
    }
    if (cfg->players == 0 || cfg->players > GR_PLAYER_COUNT) {
        return GR_ERR_INVALID_ARG;
    }

    /* Required buttons must be known before the game starts, not at 3am. */
    for (p = 0; p < cfg->players; ++p) {
        uint16_t missing = cfg->required_buttons[p] &
                           (uint16_t)~g_backend->supported_buttons[p];
        if (missing != 0) {
            for (b = 0; b < GR_BTN_COUNT; ++b) {
                if (missing & GR_BUTTON_BIT(b)) {
                    return GR_ERR_UNSUPPORTED;
                }
            }
        }
    }

    result = g_backend->init(cfg);
    if (result != GR_OK) {
        return result;
    }

    g_cfg = cfg;
    g_quit = false;
    g_in_frame = false;
    g_scene = NULL;
    gr_actor_set_limit(cfg->max_actors);
    gr_actor_clear();
    g_initialized = true;
    return GR_OK;
}

void gr_quit(void)
{
    if (!g_initialized) {
        return;
    }
    g_initialized = false;
    g_quit = true;
    if (g_backend->quit != NULL) {
        g_backend->quit();
    }
    g_backend = NULL;
    g_cfg = NULL;
    g_scene = NULL;
}

int gr_run(void)
{
    gr_fixed dt = GR_FIXED_ONE / 60;

    if (!g_initialized) {
        return 1;
    }
    if (g_cfg->game_init != NULL) {
        g_cfg->game_init();
    }
    while (!gr_quit_requested()) {
        gr_begin_frame();
        if (g_scene != NULL && g_scene->update != NULL) {
            g_scene->update(dt);
        }
        if (g_cfg->game_update != NULL) {
            g_cfg->game_update(dt);
        }
        gr_actor_update_all(dt);
        if (g_scene != NULL && g_scene->draw != NULL) {
            g_scene->draw();
        }
        if (g_cfg->game_draw != NULL) {
            g_cfg->game_draw();
        }
        gr_draw_frame();
        gr_end_frame();
    }
    gr_quit();
    return 0;
}

void gr_begin_frame(void)
{
    if (g_initialized && g_backend->frame_begin != NULL) {
        g_backend->frame_begin();
    }
    g_in_frame = true;
}

void gr_end_frame(void)
{
    if (g_initialized && g_backend->frame_end != NULL) {
        g_backend->frame_end();
    }
    g_in_frame = false;
}

void gr_draw_frame(void)
{
    gr_actor *actors[GR_MAX_ACTORS];
    uint8_t count = gr_actor_list(actors, GR_MAX_ACTORS);
    const gr_bg *bg = (g_scene != NULL && g_scene->bg != NULL &&
                       g_scene->bg->visible) ? g_scene->bg : NULL;

    if (g_initialized && g_backend->frame_draw != NULL) {
        g_backend->frame_draw(bg, actors, count);
    }
}

bool gr_quit_requested(void)
{
    return g_quit || (g_initialized && g_backend->quit_requested != NULL &&
                      g_backend->quit_requested());
}

void gr_request_quit(void)
{
    g_quit = true;
}

uint32_t gr_ticks(void)
{
    return g_initialized && g_backend->ticks != NULL ? g_backend->ticks() : 0;
}

const gr_backend *gr_backend_get(void)
{
    return g_backend;
}

/* Scenes --------------------------------------------------------------- */

gr_result gr_scene_load(gr_scene *scene)
{
    if (!g_initialized || scene == NULL) {
        return GR_ERR_INVALID_ARG;
    }
    if (g_scene != NULL && g_scene != scene && g_scene->unload != NULL) {
        g_scene->unload();
    }
    gr_actor_clear();
    g_scene = scene;
    if (scene->load != NULL) {
        scene->load();
    }
    return GR_OK;
}

gr_scene *gr_scene_current(void)
{
    return g_scene;
}

/* Sprite helpers ------------------------------------------------------- */

gr_result gr_palette_load(uint8_t slot, const gr_color *colors, uint8_t count)
{
    if (!g_initialized || colors == NULL ||
        slot >= GR_MAX_PALETTES || count == 0 || count > GR_PALETTE_COLORS) {
        return GR_ERR_INVALID_ARG;
    }
    if (g_backend->palette_load != NULL) {
        g_backend->palette_load(slot, colors, count);
    }
    return GR_OK;
}

void gr_bg_set_scroll(gr_bg *bg, int16_t x, int16_t y)
{
    if (bg != NULL) {
        bg->scroll_x = x;
        bg->scroll_y = y;
    }
}

void gr_sprite_show(gr_sprite *s, uint8_t pal_slot, int16_t x, int16_t y)
{
    if (s != NULL) {
        s->pal_slot = pal_slot;
        s->x = x;
        s->y = y;
        s->visible = true;
    }
}

void gr_sprite_hide(gr_sprite *s)
{
    if (s != NULL) {
        s->visible = false;
    }
}

void gr_sprite_set_frame(gr_sprite *s, uint8_t frame)
{
    if (s != NULL) {
        s->frame = frame;
    }
}

void gr_sprite_set_flip(gr_sprite *s, bool x, bool y)
{
    if (s != NULL) {
        s->flip = (uint8_t)((x ? GR_FLIP_X : 0u) | (y ? GR_FLIP_Y : 0u));
    }
}

/* Input ---------------------------------------------------------------- */

static bool valid_pad(gr_player player, gr_button button)
{
    return g_initialized && g_backend != NULL &&
           player < GR_PLAYER_COUNT && button < GR_BTN_COUNT;
}

bool gr_pad_down(gr_player player, gr_button button)
{
    return valid_pad(player, button) && g_backend->pad_down != NULL &&
           g_backend->pad_down(player, button);
}

bool gr_pad_pressed(gr_player player, gr_button button)
{
    return valid_pad(player, button) && g_backend->pad_pressed != NULL &&
           g_backend->pad_pressed(player, button);
}

bool gr_pad_released(gr_player player, gr_button button)
{
    return valid_pad(player, button) && g_backend->pad_released != NULL &&
           g_backend->pad_released(player, button);
}

/* Audio ---------------------------------------------------------------- */

gr_result gr_music_play(const gr_song *song)
{
    if (!g_initialized || song == NULL) {
        return GR_ERR_INVALID_ARG;
    }
    if (g_backend->music_play == NULL) {
        return GR_ERR_UNSUPPORTED;
    }
    return g_backend->music_play(song);
}

void gr_music_stop(void)
{
    if (g_initialized && g_backend->music_stop != NULL) {
        g_backend->music_stop();
    }
}

void gr_sfx_play(uint16_t sfx_id, uint8_t channel)
{
    if (g_initialized && g_backend->sfx_play != NULL &&
        channel < GR_AUDIO_CHANNELS && sfx_id < g_cfg->sfx_count) {
        g_backend->sfx_play(sfx_id, channel);
    }
}

/* Suppresses an unused-variable warning in builds without a frame loop. */
extern int gr_core_frame_in_progress(void);
int gr_core_frame_in_progress(void)
{
    return g_in_frame ? 1 : 0;
}
