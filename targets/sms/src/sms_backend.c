/*
 * Sega Master System / Game Gear backend (SDCC + devkitSMS).
 *
 * The portable core owns actors and scenes; this file translates the shared
 * API into SMS VDP tile/map writes, sprite attributes, joypad reads and simple
 * PSG tones. Video RAM writes are deferred to the vblank window.
 */
#include <SMSlib.h>
#include <gramma/gramma.h>
#include <gramma/internal/backend.h>
#include <gramma/overlay.h>
#include <gramma/target/sms/mapper.h>
#include <string.h>

#ifndef GR_SMS_ROM_BANKS
#  define GR_SMS_ROM_BANKS 2u
#endif

#define SMS_TILE_MAP_W   32u
#define SMS_TILE_MAP_H   28u
#define SMS_BG_TILES     256u
#define SMS_SPRITE_TILES 256u
#define SMS_MAX_SPRITES  64u
#define SMS_PSG_DIVISOR  111860u

#ifdef TARGET_GG
typedef uint16_t gr_sms_palette_color;
/* SMSlib exposes the Game Gear START button as a separate status bit. */
#  define GR_SMS_P1_START_KEY GG_KEY_START
#  define GR_SMS_P2_START_KEY GG_KEY_START
#else
typedef uint8_t gr_sms_palette_color;
/* The Master System has no START button; button 1 is the conventional alias. */
#  define GR_SMS_P1_START_KEY PORT_A_KEY_1
#  define GR_SMS_P2_START_KEY PORT_B_KEY_1
#endif

static __sfr __at 0x7f gr_sms_psg_port;

static const gr_config *g_cfg;
static bool g_down[GR_PLAYER_COUNT][GR_BTN_COUNT];
static bool g_prev[GR_PLAYER_COUNT][GR_BTN_COUNT];
static uint8_t g_bkg_map[SMS_TILE_MAP_W * SMS_TILE_MAP_H];
static const gr_tileset *g_bkg_tileset;
static const gr_map *g_bkg_source;
static const gr_bg *g_pending_bg;
static const gr_tileset *g_sprite_tileset;

static const gr_song *g_song;
static uint16_t g_note_index;
static uint16_t g_started_index;
static uint16_t g_note_elapsed_frames;
static uint16_t g_sfx_frames;

/* A readable default palette. Games should call gr_palette_load() with their
 * generated asset palettes; these entries keep the shipped demo visible when
 * it uses the portable API without target-specific palette code. */
static const gr_color g_default_bg_palette[16] = {
    GR_RGB(0, 0, 0), GR_RGB(8, 8, 9), GR_RGB(4, 14, 6), GR_RGB(3, 12, 5),
    GR_RGB(26, 7, 7), GR_RGB(29, 29, 29), GR_RGB(28, 28, 28), GR_RGB(2, 2, 2),
    GR_RGB(30, 30, 30), GR_RGB(8, 6, 2), GR_RGB(4, 4, 20), GR_RGB(20, 4, 4),
    GR_RGB(4, 20, 4), GR_RGB(20, 20, 4), GR_RGB(20, 4, 20), GR_RGB(4, 20, 20)
};
static const gr_color g_default_sprite_palette[16] = {
    GR_RGB(0, 0, 0), GR_RGB(4, 12, 27), GR_RGB(3, 3, 3), GR_RGB(18, 27, 31),
    GR_RGB(31, 28, 11), GR_RGB(27, 6, 6), GR_RGB(28, 12, 4), GR_RGB(31, 27, 10),
    GR_RGB(31, 30, 26), GR_RGB(11, 4, 2), GR_RGB(4, 8, 20), GR_RGB(20, 4, 4),
    GR_RGB(4, 20, 4), GR_RGB(20, 20, 4), GR_RGB(20, 4, 20), GR_RGB(4, 20, 20)
};

static void sms_mapper_bank_write(uint16_t bank, void *user)
{
    (void)user;
    SMS_mapROMBank((unsigned char)bank);
}

static gr_sms_palette_color sms_color(gr_color color)
{
    uint8_t r = (uint8_t)((color >> 10) & 0x1fu);
    uint8_t g = (uint8_t)((color >> 5) & 0x1fu);
    uint8_t b = (uint8_t)(color & 0x1fu);
#ifdef TARGET_GG
    return (gr_sms_palette_color)((r >> 1) | ((uint16_t)(g >> 1) << 4) |
                                  ((uint16_t)(b >> 1) << 8));
#else
    return (gr_sms_palette_color)((uint8_t)((b >> 3) << 4) |
                                  (uint8_t)((g >> 3) << 2) | (uint8_t)(r >> 3));
#endif
}

static void sms_set_palette_color(bool sprite, uint8_t entry, gr_color color)
{
#ifdef TARGET_GG
    if (sprite) {
        GG_setSpritePaletteColor(entry, sms_color(color));
    } else {
        GG_setBGPaletteColor(entry, sms_color(color));
    }
#else
    if (sprite) {
        SMS_setSpritePaletteColor(entry, sms_color(color));
    } else {
        SMS_setBGPaletteColor(entry, sms_color(color));
    }
#endif
}

static gr_result sms_init(const gr_config *cfg)
{
    uint8_t i;

    /* The mapper state selects bank 2 through sms_mapper_bank_write() when the
     * ROM has a switchable slot. A plain two-bank ROM must not write $FFFF. */
    (void)gr_sms_mapper_runtime_init((uint8_t)GR_SMS_ROM_BANKS,
                                     sms_mapper_bank_write, NULL);

    g_cfg = cfg;
    g_bkg_tileset = NULL;
    g_bkg_source = NULL;
    g_pending_bg = NULL;
    g_sprite_tileset = NULL;
    g_song = NULL;
    g_sfx_frames = 0u;
    g_started_index = 0xffffu;
    memset(g_down, 0, sizeof(g_down));
    memset(g_prev, 0, sizeof(g_prev));

    SMS_init();
    SMS_displayOff();
    SMS_useFirstHalfTilesforSprites(0);  /* sprites use VRAM tiles 256..511 */
    SMS_setSpriteMode(SPRITEMODE_NORMAL);
    SMS_setBGScrollX(0);
    SMS_setBGScrollY(0);
    for (i = 0; i < 16u; ++i) {
        sms_set_palette_color(false, i, g_default_bg_palette[i]);
        sms_set_palette_color(true, i, g_default_sprite_palette[i]);
    }
    SMS_initSprites();
    SMS_displayOn();
    return GR_OK;
}

static void sms_quit(void)
{
    gr_sms_psg_port = 0x9fu;             /* channel 1 volume: silent */
    SMS_displayOff();
    g_song = NULL;
    g_cfg = NULL;
}

static void sms_frame_begin(void)
{
    unsigned int keys;
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
    keys = SMS_getKeysStatus();
    g_down[0][GR_BTN_UP] = (keys & PORT_A_KEY_UP) != 0u;
    g_down[0][GR_BTN_DOWN] = (keys & PORT_A_KEY_DOWN) != 0u;
    g_down[0][GR_BTN_LEFT] = (keys & PORT_A_KEY_LEFT) != 0u;
    g_down[0][GR_BTN_RIGHT] = (keys & PORT_A_KEY_RIGHT) != 0u;
    g_down[0][GR_BTN_A] = (keys & PORT_A_KEY_1) != 0u;
    g_down[0][GR_BTN_B] = (keys & PORT_A_KEY_2) != 0u;
    g_down[0][GR_BTN_START] = (keys & GR_SMS_P1_START_KEY) != 0u;
    if (g_cfg->players > 1) {
        g_down[1][GR_BTN_UP] = (keys & PORT_B_KEY_UP) != 0u;
        g_down[1][GR_BTN_DOWN] = (keys & PORT_B_KEY_DOWN) != 0u;
        g_down[1][GR_BTN_LEFT] = (keys & PORT_B_KEY_LEFT) != 0u;
        g_down[1][GR_BTN_RIGHT] = (keys & PORT_B_KEY_RIGHT) != 0u;
        g_down[1][GR_BTN_A] = (keys & PORT_B_KEY_1) != 0u;
        g_down[1][GR_BTN_B] = (keys & PORT_B_KEY_2) != 0u;
        g_down[1][GR_BTN_START] = (keys & GR_SMS_P2_START_KEY) != 0u;
    }
}

/* Build the full 32x28 map outside vblank; SMS VRAM writes happen in
 * sms_frame_end() so visible scanlines never see a half-updated nametable. */
static void sms_prepare_background(const gr_bg *bg)
{
    uint8_t x, y;

    if (bg->tileset == NULL || bg->map == NULL || bg->map->tiles == NULL ||
        bg->tileset->tile_count > SMS_BG_TILES) {
        return;
    }
    for (y = 0; y < SMS_TILE_MAP_H; ++y) {
        for (x = 0; x < SMS_TILE_MAP_W; ++x) {
            uint8_t mx = (uint8_t)(x % bg->map->width);
            uint8_t my = (uint8_t)(y % bg->map->height);
            uint16_t index = bg->map->tiles[my * bg->map->width + mx];
            g_bkg_map[y * SMS_TILE_MAP_W + x] = (uint8_t)index;
        }
    }
    g_pending_bg = bg;
}

static void sms_upload_background(void)
{
    if (g_pending_bg == NULL) {
        return;
    }
    SMS_loadTiles(g_pending_bg->tileset->tiles, 0,
                  (unsigned int)g_pending_bg->tileset->tile_count * 32u);
    SMS_loadTileMapArea(0, 0, g_bkg_map, SMS_TILE_MAP_W, SMS_TILE_MAP_H);
    g_bkg_tileset = g_pending_bg->tileset;
    g_bkg_source = g_pending_bg->map;
    g_pending_bg = NULL;
}

static void sms_frame_draw(const gr_bg *bg, gr_actor *const *actors,
                           uint8_t actor_count)
{
    uint8_t i, used = 0u;

    if (bg != NULL && (bg->tileset != g_bkg_tileset ||
                       bg->map != g_bkg_source)) {
        sms_prepare_background(bg);
    }
    if (bg != NULL) {
        SMS_setBGScrollX((unsigned char)bg->scroll_x);
        SMS_setBGScrollY((unsigned char)bg->scroll_y);
    }

    SMS_initSprites();
    for (i = 0; i < actor_count; ++i) {
        const gr_sprite *s = &actors[i]->sprite;
        uint8_t fw = s->frame_w ? s->frame_w : 1u;
        uint8_t fh = s->frame_h ? s->frame_h : 1u;
        uint8_t ty, tx;

        if (s->tileset == NULL) {
            continue;
        }
        if (s->tileset != g_sprite_tileset) {
            uint16_t bytes = (uint16_t)s->tileset->tile_count * 32u;
            if (gr_overlay_tiles(SMS_SPRITE_TILES, s->tileset->tiles,
                                 bytes, true) == GR_OK) {
                g_sprite_tileset = s->tileset;
            }
        }
        if (!s->visible) {
            continue;
        }
        for (ty = 0; ty < fh && used < SMS_MAX_SPRITES; ++ty) {
            for (tx = 0; tx < fw && used < SMS_MAX_SPRITES; ++tx) {
                uint8_t tile = (uint8_t)(s->frame * fw * fh + ty * fw + tx);
                /* SAT tile indices are absolute VRAM tile numbers. Sprite art
                 * is uploaded to the upper 256 tiles, so add the sprite base
                 * here instead of letting sprites reuse background tiles. */
                if (tile >= SMS_SPRITE_TILES) {
                    continue;
                }
                SMS_addSprite((unsigned int)(s->x + tx * 8),
                              (unsigned int)(s->y + ty * 8),
                              (unsigned int)(SMS_SPRITE_TILES + tile));
                ++used;
            }
        }
    }
    while (used < SMS_MAX_SPRITES) {
        SMS_hideSprite((signed char)used);
        ++used;
    }
}

static void sms_start_tone(uint8_t channel, uint16_t freq, uint8_t volume)
{
    uint16_t period;
    uint8_t shift = (uint8_t)(channel << 5);
    uint8_t attenuation;

    if (freq == 0u || volume == 0u) {
        gr_sms_psg_port = (uint8_t)(0x80u | shift | 0x10u);
        gr_sms_psg_port = 0x0fu;
        return;
    }
    period = (uint16_t)(SMS_PSG_DIVISOR / freq);
    if (period == 0u) {
        period = 1u;
    } else if (period > 1023u) {
        period = 1023u;
    }
    attenuation = (uint8_t)(15u - (volume > 15u ? 15u : volume));
    gr_sms_psg_port = (uint8_t)(0x80u | shift | (period & 0x0fu));
    gr_sms_psg_port = (uint8_t)(period >> 4);
    gr_sms_psg_port = (uint8_t)(0x80u | shift | 0x10u);
    gr_sms_psg_port = attenuation;
}

static void sms_update_music(void)
{
    const gr_note *note;

    if (g_song == NULL || g_song->note_count == 0u || g_song->bpm == 0u) {
        return;
    }
    ++g_note_elapsed_frames;
    note = &g_song->notes[g_note_index];
    {
        uint16_t frames = (uint16_t)((uint32_t)note->ticks * 60u /
                                     g_song->bpm / 4u);
        if (frames == 0u) {
            frames = 1u;
        }
        while (g_note_elapsed_frames >= frames) {
            g_note_elapsed_frames = (uint16_t)(g_note_elapsed_frames - frames);
            ++g_note_index;
            if (g_note_index >= g_song->note_count) {
                if (!g_song->loop) {
                    g_song = NULL;
                    sms_start_tone(0, 0, 0);
                    return;
                }
                g_note_index = 0u;
            }
            note = &g_song->notes[g_note_index];
            frames = (uint16_t)((uint32_t)note->ticks * 60u /
                                g_song->bpm / 4u);
            if (frames == 0u) {
                frames = 1u;
            }
        }
    }
    if (g_note_index != g_started_index) {
        sms_start_tone(0, note->freq_hz, note->volume);
        g_started_index = g_note_index;
    }
}

static void sms_frame_end(void)
{
    SMS_waitForVBlank();
    sms_upload_background();
    (void)gr_overlay_flush();
    SMS_copySpritestoSAT();
    if (g_sfx_frames > 0u && --g_sfx_frames == 0u) {
        sms_start_tone(1, 0, 0);
    }
    sms_update_music();
}

static bool sms_pad_down(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return g_down[player][button];
}

static bool sms_pad_pressed(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return g_down[player][button] && !g_prev[player][button];
}

static bool sms_pad_released(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return !g_down[player][button] && g_prev[player][button];
}

static void sms_palette_load(uint8_t slot, const gr_color *colors,
                             uint8_t count)
{
    uint8_t i;
    bool sprite = (slot & 1u) != 0u;

    for (i = 0; i < count && i < 16u; ++i) {
        sms_set_palette_color(sprite, i, colors[i]);
    }
}

static gr_result sms_music_play(const gr_song *song)
{
    g_song = song;
    g_note_index = 0u;
    g_started_index = 0xffffu;
    g_note_elapsed_frames = 0u;
    if (song != NULL && song->note_count > 0u) {
        sms_start_tone(0, song->notes[0].freq_hz, song->notes[0].volume);
        g_started_index = 0u;
    }
    return GR_OK;
}

static void sms_music_stop(void)
{
    g_song = NULL;
    sms_start_tone(0, 0, 0);
}

static void sms_sfx_play(uint16_t id, uint8_t channel)
{
    const gr_sfx_def *def;
    uint16_t freq = 440u;
    uint8_t psg_channel = channel == 0u ? 1u : (uint8_t)(channel & 1u);

    (void)channel;
    if (g_cfg == NULL || id >= g_cfg->sfx_count) {
        return;
    }
    def = g_cfg->sfx[id];
    if (def->wave != GR_WAVE_PCM && def->freq_hz > 0u) {
        freq = def->freq_hz;
    }
    sms_start_tone(psg_channel, freq, def->volume);
    g_sfx_frames = (uint16_t)(def->duration_ms / 17u);
}

static uint32_t sms_ticks(void)
{
    static uint32_t counter;
    return ++counter * 17u;
}

static bool sms_quit_requested(void)
{
    return false;
}

/* Overlay hooks run only from sms_frame_end, after SMS_waitForVBlank(). */
static gr_result sms_overlay_tiles(uint8_t dest, const uint8_t *data,
                                   uint16_t count, bool sprite)
{
    uint16_t tiles;

    (void)sprite;                 /* the destination VRAM half selects the bank */
    if (count == 0u || (count & 0x1fu) != 0u) {
        return GR_ERR_INVALID_ARG;
    }
    tiles = (uint16_t)(count >> 5);
    if ((uint16_t)dest + tiles > 512u) {
        return GR_ERR_INVALID_ARG;
    }
    SMS_loadTiles(data, dest, count);
    return GR_OK;
}

static gr_result sms_overlay_nametable(uint8_t x, uint8_t y, uint8_t w,
                                       uint8_t h, const uint8_t *tiles)
{
    if ((uint16_t)x + w > SMS_TILE_MAP_W ||
        (uint16_t)y + h > SMS_TILE_MAP_H) {
        return GR_ERR_INVALID_ARG;
    }
    SMS_loadTileMapArea(x, y, tiles, w, h);
    return GR_OK;
}

const gr_backend gr_backend_sms = {
    "sms",
    { GR_BUTTON_BIT(GR_BTN_UP) | GR_BUTTON_BIT(GR_BTN_DOWN) |
      GR_BUTTON_BIT(GR_BTN_LEFT) | GR_BUTTON_BIT(GR_BTN_RIGHT) |
      GR_BUTTON_BIT(GR_BTN_A) | GR_BUTTON_BIT(GR_BTN_B) |
      GR_BUTTON_BIT(GR_BTN_START),
      GR_BUTTON_BIT(GR_BTN_UP) | GR_BUTTON_BIT(GR_BTN_DOWN) |
      GR_BUTTON_BIT(GR_BTN_LEFT) | GR_BUTTON_BIT(GR_BTN_RIGHT) |
      GR_BUTTON_BIT(GR_BTN_A) | GR_BUTTON_BIT(GR_BTN_B) |
      GR_BUTTON_BIT(GR_BTN_START) },
    sms_init,
    sms_quit,
    sms_frame_begin,
    sms_frame_draw,
    sms_frame_end,
    sms_pad_down,
    sms_pad_pressed,
    sms_pad_released,
    sms_palette_load,
    sms_music_play,
    sms_music_stop,
    sms_sfx_play,
    sms_ticks,
    sms_quit_requested,
    sms_overlay_tiles,
    sms_overlay_nametable
};
