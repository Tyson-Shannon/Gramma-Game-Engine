/*
 * Game Boy / GBC backend (GBDK-2020).
 *
 * The portable core owns actors and scenes; this file only translates the
 * shared API into tile maps, OAM, joypad and APU register writes.
 */
#include <gb/gb.h>
#include <gb/hardware.h>
#include <gramma/gramma.h>
#include <gramma/internal/backend.h>
#include <gramma/overlay.h>
#include <gramma/target/gb/mapper.h>
#include <string.h>

#define GB_TILE_MAP_W   32u
#define GB_TILE_MAP_H   32u
#define GB_SPRITE_TILES 64u
#define GB_MAX_OAM      40u

static const gr_config *g_cfg;
static bool g_down[GR_PLAYER_COUNT][GR_BTN_COUNT];
static bool g_prev[GR_PLAYER_COUNT][GR_BTN_COUNT];
static uint8_t g_bkg_map[GB_TILE_MAP_W * GB_TILE_MAP_H];
static const gr_tileset *g_bkg_tileset;
static const gr_map *g_bkg_source;
static const gr_bg *g_pending_bg;
static const gr_tileset *g_sprite_tileset;

static const gr_song *g_song;
static uint16_t g_note_index;
static uint16_t g_started_index;
static uint16_t g_note_elapsed_frames;
static uint16_t g_sfx_frames;

/* Translate a generic MBC bank selection into GBDK's hardware writes. */
static void gb_mapper_bank_write(uint8_t kind, uint16_t bank, void *user)
{
    (void)user;
    /* Do not mask interrupts here: callers that need to read banked data keep
     * their own CRITICAL window, and a nested EI here would expose an ISR to
     * the wrong ROM bank before the caller restores bank 1. */
    if (kind == GR_GB_BANK_ROM) {
#if GR_GB_MAPPER == 5
        SWITCH_ROM_MBC5((uint8_t)bank);
#else
        SWITCH_ROM((uint8_t)bank);
#endif
#if GR_GB_RAM_BANKS > 0u
    } else if (kind == GR_GB_BANK_RAM) {
        SWITCH_RAM((uint8_t)bank);
#endif
    }
}

static gr_result gb_init(const gr_config *cfg)
{
    uint8_t i;

#if GR_GB_RAM_BANKS > 0u
    ENABLE_RAM;
#endif
    /* The build-time [mapper.gb] layout is installed before game_init() so
     * games can use gr_gb_mapper_rom_banks() immediately. */
    (void)gr_gb_mapper_runtime_init((gr_gb_mapper)GR_GB_MAPPER,
                                    (uint8_t)GR_GB_ROM_BANKS,
                                    (uint8_t)GR_GB_RAM_BANKS,
                                    gb_mapper_bank_write, NULL);

    g_cfg = cfg;
    g_bkg_tileset = NULL;
    g_bkg_source = NULL;
    g_pending_bg = NULL;
    g_sprite_tileset = NULL;
    g_song = NULL;
    g_sfx_frames = 0;
    g_started_index = 0xffffu;
    memset(g_down, 0, sizeof(g_down));
    memset(g_prev, 0, sizeof(g_prev));

    DISPLAY_OFF;
    SPRITES_8x8;
    VBK_REG = VBK_BANK_0;
    BGP_REG = DMG_PALETTE(DMG_WHITE, DMG_LITE_GRAY,
                          DMG_DARK_GRAY, DMG_BLACK);
    OBP0_REG = DMG_PALETTE(DMG_WHITE, DMG_LITE_GRAY,
                           DMG_DARK_GRAY, DMG_BLACK);
    OBP1_REG = DMG_PALETTE(DMG_WHITE, DMG_LITE_GRAY,
                           DMG_DARK_GRAY, DMG_BLACK);

    for (i = 0; i < GB_MAX_OAM; ++i) {
        move_sprite(i, 0, 160);
    }
    SHOW_BKG;
    SHOW_SPRITES;
    DISPLAY_ON;

    NR52_REG = 0x80; /* APU on */
    NR50_REG = 0x77;
    NR51_REG = 0xFF;
    return GR_OK;
}

static void gb_quit(void)
{
    NR52_REG = 0;
    DISPLAY_OFF;
    g_song = NULL;
    g_cfg = NULL;
}

static void gb_frame_begin(void)
{
    uint8_t keys = joypad();
    uint8_t p, b;

    for (p = 0; p < GR_PLAYER_COUNT; ++p) {
        for (b = 0; b < GR_BTN_COUNT; ++b) {
            g_prev[p][b] = g_down[p][b];
            g_down[p][b] = false;
        }
    }
    if (g_cfg == NULL || g_cfg->players == 0) {
        return;
    }
    g_down[0][GR_BTN_UP] = (keys & J_UP) != 0;
    g_down[0][GR_BTN_DOWN] = (keys & J_DOWN) != 0;
    g_down[0][GR_BTN_LEFT] = (keys & J_LEFT) != 0;
    g_down[0][GR_BTN_RIGHT] = (keys & J_RIGHT) != 0;
    g_down[0][GR_BTN_A] = (keys & J_A) != 0;
    g_down[0][GR_BTN_B] = (keys & J_B) != 0;
    g_down[0][GR_BTN_START] = (keys & J_START) != 0;
    g_down[0][GR_BTN_SELECT] = (keys & J_SELECT) != 0;
}

/* Build the expanded 32x32 map outside vblank; the VRAM writes are deferred
 * to gb_frame_end so tile/map uploads never happen on visible scanlines. */
static void gb_prepare_background(const gr_bg *bg)
{
    uint8_t x, y;

    if (bg->tileset == NULL || bg->map == NULL || bg->map->tiles == NULL ||
        bg->tileset->tile_count > GB_SPRITE_TILES) {
        return;
    }
    for (y = 0; y < GB_TILE_MAP_H; ++y) {
        for (x = 0; x < GB_TILE_MAP_W; ++x) {
            uint8_t mx = (uint8_t)(x % bg->map->width);
            uint8_t my = (uint8_t)(y % bg->map->height);
            uint16_t index = bg->map->tiles[my * bg->map->width + mx];
            g_bkg_map[y * GB_TILE_MAP_W + x] = (uint8_t)index;
        }
    }
    g_pending_bg = bg;
}

static void gb_upload_background(void)
{
    if (g_pending_bg == NULL) {
        return;
    }
    set_bkg_data(0, g_pending_bg->tileset->tile_count,
                 g_pending_bg->tileset->tiles);
    VBK_REG = VBK_BANK_0;
    set_bkg_tiles(0, 0, GB_TILE_MAP_W, GB_TILE_MAP_H, g_bkg_map);
    g_bkg_tileset = g_pending_bg->tileset;
    g_bkg_source = g_pending_bg->map;
    g_pending_bg = NULL;
}

static void gb_frame_draw(const gr_bg *bg, gr_actor *const *actors,
                          uint8_t actor_count)
{
    uint8_t i, used = 0;

    if (bg != NULL && (bg->tileset != g_bkg_tileset ||
                       bg->map != g_bkg_source)) {
        gb_prepare_background(bg);
    }
    if (bg != NULL) {
        SCX_REG = (uint8_t)bg->scroll_x;
        SCY_REG = (uint8_t)bg->scroll_y;
    }

    for (i = 0; i < actor_count; ++i) {
        const gr_sprite *s = &actors[i]->sprite;
        uint8_t fw = s->frame_w ? s->frame_w : 1;
        uint8_t fh = s->frame_h ? s->frame_h : 1;
        uint8_t ty, tx;

        if (s->tileset == NULL) {
            continue;
        }
        if (s->tileset != g_sprite_tileset) {
            uint16_t bytes = (uint16_t)s->tileset->tile_count * 16u;
            if (gr_overlay_tiles(GB_SPRITE_TILES, s->tileset->tiles,
                                 bytes, true) == GR_OK) {
                g_sprite_tileset = s->tileset;
            }
        }
        if (!s->visible) {
            continue;
        }
        for (ty = 0; ty < fh && used < GB_MAX_OAM; ++ty) {
            for (tx = 0; tx < fw && used < GB_MAX_OAM; ++tx) {
                uint8_t tile = (uint8_t)(GB_SPRITE_TILES +
                    (uint16_t)s->frame * fw * fh + ty * fw + tx);
                uint8_t props = s->pal_slot ? S_PALETTE : 0u;
                if (s->flip & GR_FLIP_X) {
                    props |= S_FLIPX;
                }
                if (s->flip & GR_FLIP_Y) {
                    props |= S_FLIPY;
                }
                set_sprite_tile(used, tile);
                set_sprite_prop(used, props);
                move_sprite(used,
                            (uint8_t)(s->x + tx * 8 + 8),
                            (uint8_t)(s->y + ty * 8 + 16));
                ++used;
            }
        }
    }
    while (used < GB_MAX_OAM) {
        move_sprite(used, 0, 160);
        ++used;
    }
}

static void gb_start_tone(uint8_t channel, uint16_t freq, uint8_t volume)
{
    uint16_t divisor;

    if (freq == 0 || volume == 0) {
        if (channel == 0) {
            NR12_REG = 0;
        } else {
            NR22_REG = 0;
        }
        return;
    }
    divisor = 2048u - (131072u / freq);
    if (divisor > 2047u) {
        divisor = 0;
    }
    if (channel == 0) {
        NR11_REG = 0x80;
        NR12_REG = (uint8_t)((volume > 15 ? 15 : volume) << 4);
        NR13_REG = (uint8_t)(divisor & 0xffu);
        NR14_REG = (uint8_t)(0x80u | ((divisor >> 8) & 0x07u));
    } else {
        NR21_REG = 0x80;
        NR22_REG = (uint8_t)((volume > 15 ? 15 : volume) << 4);
        NR23_REG = (uint8_t)(divisor & 0xffu);
        NR24_REG = (uint8_t)(0x80u | ((divisor >> 8) & 0x07u));
    }
}

static void gb_frame_end(void)
{
    wait_vbl_done();
    /* VRAM is writable now; perform all scene and overlay uploads before any
     * audio work extends the frame. */
    gb_upload_background();
    (void)gr_overlay_flush();
    if (g_sfx_frames > 0 && --g_sfx_frames == 0) {
        NR22_REG = 0;
    }
    if (g_song == NULL || g_song->note_count == 0 || g_song->bpm == 0) {
        return;
    }
    ++g_note_elapsed_frames;
    {
        const gr_note *note = &g_song->notes[g_note_index];
        uint16_t frames = (uint16_t)((uint32_t)note->ticks * 60u /
                                     g_song->bpm / 4u);
        if (frames == 0) {
            frames = 1;
        }
        while (g_note_elapsed_frames >= frames) {
            g_note_elapsed_frames = (uint16_t)(g_note_elapsed_frames - frames);
            ++g_note_index;
            if (g_note_index >= g_song->note_count) {
                if (!g_song->loop) {
                    g_song = NULL;
                    NR12_REG = 0;
                    return;
                }
                g_note_index = 0;
            }
            note = &g_song->notes[g_note_index];
            frames = (uint16_t)((uint32_t)note->ticks * 60u /
                                g_song->bpm / 4u);
            if (frames == 0) {
                frames = 1;
            }
        }
        if (g_note_index != g_started_index) {
            gb_start_tone(0, note->freq_hz, note->volume);
            g_started_index = g_note_index;
        }
    }
}

static bool gb_pad_down(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return g_down[player][button];
}

static bool gb_pad_pressed(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return g_down[player][button] && !g_prev[player][button];
}

static bool gb_pad_released(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return !g_down[player][button] && g_prev[player][button];
}

static uint8_t gb_shade(gr_color color)
{
    uint16_t r = (uint16_t)((color >> 10) & 0x1fu);
    uint16_t g = (uint16_t)((color >> 5) & 0x1fu);
    uint16_t b = (uint16_t)(color & 0x1fu);
    uint16_t luma = (uint16_t)((r * 3u + g * 6u + b) / 10u);
    if (luma > 23) {
        return DMG_WHITE;
    }
    if (luma > 15) {
        return DMG_LITE_GRAY;
    }
    if (luma > 7) {
        return DMG_DARK_GRAY;
    }
    return DMG_BLACK;
}

static void gb_palette_load(uint8_t slot, const gr_color *colors, uint8_t count)
{
    uint8_t shade[4] = { DMG_WHITE, DMG_LITE_GRAY, DMG_DARK_GRAY, DMG_BLACK };
    uint8_t i;
    for (i = 0; i < count && i < 4; ++i) {
        shade[i] = gb_shade(colors[i]);
    }
    if (slot == 0) {
        BGP_REG = DMG_PALETTE(shade[0], shade[1], shade[2], shade[3]);
        OBP0_REG = DMG_PALETTE(shade[0], shade[1], shade[2], shade[3]);
    } else {
        OBP1_REG = DMG_PALETTE(shade[0], shade[1], shade[2], shade[3]);
    }
}

static gr_result gb_music_play(const gr_song *song)
{
    g_song = song;
    g_note_index = 0;
    g_started_index = 0xffffu;
    g_note_elapsed_frames = 0;
    if (song != NULL && song->note_count > 0) {
        gb_start_tone(0, song->notes[0].freq_hz, song->notes[0].volume);
        g_started_index = 0;
    }
    return GR_OK;
}

static void gb_music_stop(void)
{
    g_song = NULL;
    NR12_REG = 0;
}

static void gb_sfx_play(uint16_t id, uint8_t channel)
{
    const gr_sfx_def *def;
    uint16_t freq = 440;

    (void)channel;
    if (g_cfg == NULL || id >= g_cfg->sfx_count) {
        return;
    }
    def = g_cfg->sfx[id];
    if (def->wave != GR_WAVE_PCM && def->freq_hz > 0) {
        freq = def->freq_hz;
    }
    gb_start_tone(1, freq, def->volume);
    g_sfx_frames = (uint16_t)(def->duration_ms / 17u);
}

static uint32_t gb_ticks(void)
{
    /* Each portable frame is one 60 Hz tick. */
    static uint32_t counter;
    return ++counter * 17u;
}

static bool gb_quit_requested(void)
{
    return false;
}

/* Overlay hooks run only from gb_frame_end, after wait_vbl_done(). */
static gr_result gb_overlay_tiles(uint8_t dest, const uint8_t *data,
                                  uint16_t count, bool sprite)
{
    uint8_t tiles;

    if (count == 0u || (count & 0x0fu) != 0u) {
        return GR_ERR_INVALID_ARG;
    }
    tiles = (uint8_t)(count >> 4);
    if ((uint16_t)dest + tiles > 256u) {
        return GR_ERR_INVALID_ARG;
    }
    if (sprite) {
        set_sprite_data(dest, tiles, (uint8_t *)data);
    } else {
        set_bkg_data(dest, tiles, (uint8_t *)data);
    }
    return GR_OK;
}

static gr_result gb_overlay_nametable(uint8_t x, uint8_t y, uint8_t w,
                                      uint8_t h, const uint8_t *tiles)
{
    if (x + w > GB_TILE_MAP_W || y + h > GB_TILE_MAP_H) {
        return GR_ERR_INVALID_ARG;
    }
    VBK_REG = VBK_BANK_0;
    set_bkg_tiles(x, y, w, h, (uint8_t *)tiles);
    return GR_OK;
}

const gr_backend gr_backend_gb = {
    "gb",
    { GR_BUTTON_BIT(GR_BTN_UP) | GR_BUTTON_BIT(GR_BTN_DOWN) |
      GR_BUTTON_BIT(GR_BTN_LEFT) | GR_BUTTON_BIT(GR_BTN_RIGHT) |
      GR_BUTTON_BIT(GR_BTN_A) | GR_BUTTON_BIT(GR_BTN_B) |
      GR_BUTTON_BIT(GR_BTN_START) | GR_BUTTON_BIT(GR_BTN_SELECT), 0 },
    gb_init,
    gb_quit,
    gb_frame_begin,
    gb_frame_draw,
    gb_frame_end,
    gb_pad_down,
    gb_pad_pressed,
    gb_pad_released,
    gb_palette_load,
    gb_music_play,
    gb_music_stop,
    gb_sfx_play,
    gb_ticks,
    gb_quit_requested,
    gb_overlay_tiles,
    gb_overlay_nametable
};
