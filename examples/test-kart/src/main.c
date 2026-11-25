/*
 * test-kart: the shared example used to exercise every Gramma backend.
 * Scrolling tile background, animated two-player sprites, music and SFX.
 * This file is plain C against the portable API - no target-specific code.
 */
#include <gramma/gramma.h>
#include <string.h>

#include "chr_switch.h"

#if defined(GRAMMA_TARGET_NES)
#include <gramma/target/nes/mapper.h>
#endif

extern const gr_tileset kart_tileset;
extern const gr_tileset altkart_tileset;
extern const gr_tileset track_tileset;
extern const gr_map track_map;
extern const gr_sfx_def engine_sfx;

static gr_bg track;
static gr_actor *karts[GR_PLAYER_COUNT];
static bool g_prg_probe_ok;

static const gr_note theme_notes[] = {
    { 523, 4, 11, 0, GR_WAVE_SQUARE },
    { 659, 4, 11, 0, GR_WAVE_SQUARE },
    { 784, 4, 11, 0, GR_WAVE_SQUARE },
    { 659, 4, 11, 0, GR_WAVE_SQUARE },
    { 587, 4, 11, 0, GR_WAVE_TRIANGLE },
    { 698, 4, 11, 0, GR_WAVE_TRIANGLE },
    { 880, 8, 11, 0, GR_WAVE_TRIANGLE },
    { 0,   4, 0,  0, GR_WAVE_SQUARE },
};
static const gr_song theme = {
    160, sizeof(theme_notes) / sizeof(theme_notes[0]), theme_notes, true
};

static const gr_sfx_def *const sfx_table[] = { &engine_sfx };

static void kart_update(gr_actor *actor, gr_fixed dt, gr_player player)
{
    gr_fixed speed = gr_itof(96);
    gr_fixed vx = 0;
    gr_fixed vy = 0;
    gr_fixed limit_x = gr_itof(GR_SCREEN_W - 16);
    gr_fixed limit_y = gr_itof(GR_SCREEN_H - 16);
    (void)dt;

    if (gr_pad_down(player, GR_BTN_LEFT)) {
        vx = -speed;
    } else if (gr_pad_down(player, GR_BTN_RIGHT)) {
        vx = speed;
    }
    if (gr_pad_down(player, GR_BTN_UP)) {
        vy = -speed;
    } else if (gr_pad_down(player, GR_BTN_DOWN)) {
        vy = speed;
    }
    actor->vx = vx;
    actor->vy = vy;

    if (vx < 0) {
        gr_sprite_set_frame(&actor->sprite, 3);
    } else if (vx > 0) {
        gr_sprite_set_frame(&actor->sprite, 1);
    } else if (vy < 0) {
        gr_sprite_set_frame(&actor->sprite, 0);
    } else if (vy > 0) {
        gr_sprite_set_frame(&actor->sprite, 2);
    }

    if (gr_pad_pressed(player, GR_BTN_A)) {
        gr_sfx_play(0, 1);
    }
    actor->x = gr_fclamp(actor->x, 0, limit_x);
    actor->y = gr_fclamp(actor->y, 0, limit_y);
}

static void kart_update_p1(gr_actor *actor, gr_fixed dt)
{
    kart_update(actor, dt, GR_PLAYER_1);
}

static void kart_update_p2(gr_actor *actor, gr_fixed dt)
{
    kart_update(actor, dt, GR_PLAYER_2);
}

static void race_load(void)
{
    gr_actor_def def;
    uint8_t player;

    memset(&def, 0, sizeof(def));
    def.name = "kart";
    def.tileset = &kart_tileset;
    def.frame_w = 2;
    def.frame_h = 2;
    def.frame = 0;

    for (player = 0; player < GR_PLAYER_COUNT; ++player) {
        def.x = gr_itof(40 + player * 32);
        def.y = gr_itof(GR_SCREEN_H / 2);
        def.frame = player == 0 ? 0 : 2;
        def.update = player == 0 ? kart_update_p1 : kart_update_p2;
        karts[player] = gr_actor_spawn(&def);
    }
}

static void race_update(gr_fixed dt)
{
    int scroll;
    (void)dt;
    chr_switch_update();
    if (karts[0] != NULL) {
        scroll = gr_ftoi(karts[0]->x) - GR_SCREEN_W / 2;
        if (scroll < 0) {
            scroll += (int)track_map.width * 8;
        }
        if (g_prg_probe_ok) {
            scroll += 8;
        }
        gr_bg_set_scroll(&track, (int16_t)scroll, 0);
    }
}

static gr_scene race = {
    "race", &track, race_load, NULL, race_update, NULL
};

static void game_init(void)
{
    chr_switch_init();
    g_prg_probe_ok = chr_switch_probe_ok();
#if defined(GRAMMA_TARGET_NES) && defined(GR_NES_RAMCODE)
    {
        uint8_t probe = 0;
        extern const uint8_t prg_probe_data[];
        (void)prg_probe_data;
        g_prg_probe_ok = g_prg_probe_ok ||
            (gr_nes_prg_read(0u, 0u, &probe, 1u) == GR_OK &&
             probe == 0xa5u);
    }
#endif
    gr_bg_init(&track, &track_tileset, &track_map, 0);
    gr_music_play(&theme);
    gr_scene_load(&race);
}

static const gr_config config = {
    "Test Kart - Gramma",
    GR_SCREEN_W, GR_SCREEN_H,
    4,
    GR_PAD_PLAYERS,
    {
        GR_BUTTON_BIT(GR_BTN_UP) | GR_BUTTON_BIT(GR_BTN_DOWN) |
        GR_BUTTON_BIT(GR_BTN_LEFT) | GR_BUTTON_BIT(GR_BTN_RIGHT) |
        GR_BUTTON_BIT(GR_BTN_A) | GR_BUTTON_BIT(GR_BTN_B),
#if GR_PAD_PLAYERS > 1
        GR_BUTTON_BIT(GR_BTN_UP) | GR_BUTTON_BIT(GR_BTN_DOWN) |
        GR_BUTTON_BIT(GR_BTN_LEFT) | GR_BUTTON_BIT(GR_BTN_RIGHT) |
        GR_BUTTON_BIT(GR_BTN_A) | GR_BUTTON_BIT(GR_BTN_B)
#else
        0
#endif
    },
    game_init,
    NULL,
    NULL,
    sfx_table,
    sizeof(sfx_table) / sizeof(sfx_table[0])
};

int main(void)
{
    if (gr_init(&config) != GR_OK) {
        return 1;
    }
    return gr_run();
}
