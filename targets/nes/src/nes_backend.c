/*
 * NES backend (cc65, NROM / mapper 0).
 *
 * The portable core owns actors and scenes; this file translates the shared
 * API into nametable writes, OAM writes, joypad reads and APU register writes.
 * CHR is generated into the cartridge's CHR-ROM by the asset pipeline, so
 * this backend never writes the pattern tables. Configuration is deliberately
 * conservative: one 32 KB PRG bank, one 8 KB CHR bank, one nametable and 8x8
 * sprites.
 */
#include <nes.h>
#include <gramma/gramma.h>
#include <gramma/internal/backend.h>
#include <gramma/overlay.h>
#include <gramma/target/nes/mapper.h>
#include <string.h>

#define NES_CTRL          0x90u  /* NMI on, bg $0000, sprites $1000, 8x8 */
#define NES_CTRL_BASE     0x90u  /* plus the two nametable bits */
#define NES_NAMETABLE     0x2000u
#define NES_ATTR_OFFSET   0x03C0u
#define NES_PALETTE       0x3F00u
#define NES_VBLANK_FLAG   0x0070u
#define NES_SCROLL_X      0x7EE0u  /* written by nes_crt0.s during NMI */
#define NES_SCROLL_Y      0x7EE1u
#define NES_CTRL_SHADOW   0x7EE2u  /* full $2000 value, also written by NMI */
#define NES_MAX_SPRITES   64u
/* Overlay patches share the custom NMI's ppubuf flush with scrolling and the
 * palette. Cap them so a banked scene change cannot consume the whole vblank. */
#define NES_OVERLAY_VBLANK_BUDGET 64u
/* $2000 is write-only on real hardware, so keep a shadow to restore it after
 * a banked PRG read temporarily disables NMI. */
static uint8_t g_ppu_ctrl = NES_CTRL;
extern const uint8_t nes_chr_data[];
/* Absolute symbol exported by nes_crt0.s from the build-time mapper config. */
extern const uint8_t gr_nes_mapper_id;
extern const uint8_t gr_nes_prg_banks;

static const gr_config *g_cfg;

static bool g_down[GR_PLAYER_COUNT][GR_BTN_COUNT];
static bool g_prev[GR_PLAYER_COUNT][GR_BTN_COUNT];
static uint8_t g_raw[GR_PLAYER_COUNT];

static const gr_tileset *g_bkg_tileset;
static const gr_map *g_bkg_source;
static const gr_bg *g_current_bg;
static const gr_bg *g_pending_bg;
static bool g_bg_upload_pending;
static uint8_t g_bg_column;
static uint8_t g_bg_pal_slot;
static uint8_t g_bg_nametable;
static const uint8_t *g_bg_palette_map;
static uint8_t g_overlay_writes;
static volatile uint8_t *const g_scroll_x =
    (volatile uint8_t *)NES_SCROLL_X;
static volatile uint8_t *const g_scroll_y =
    (volatile uint8_t *)NES_SCROLL_Y;
static volatile uint8_t *const g_ctrl_shadow =
    (volatile uint8_t *)NES_CTRL_SHADOW;

static uint16_t nes_nametable_base(uint8_t nametable)
{
    return (uint16_t)(NES_NAMETABLE + (uint16_t)(nametable & 3u) * 0x0400u);
}

static const gr_tileset *g_sprite_tileset;
static uint8_t g_sprite_tile_base;

static uint8_t g_palette[8][GR_PALETTE_COLORS];
static const gr_tileset *g_palette_source[8];
static bool g_palette_dirty;

static uint8_t g_oam[NES_MAX_SPRITES * 4u];

static const gr_song *g_song;
static uint16_t g_note_index;
static uint16_t g_started_index;
static uint16_t g_note_elapsed_frames;
static uint16_t g_sfx_frames;
static uint8_t g_music_channel; /* 0 pulse, 1 triangle, 2 noise, 0xff none */

/* The cc65 2.19 NMI sets VBLANK_FLAG ($70) but never clears it. waitvsync()
 * polls PPU_STATUS directly and races with the NMI, so use the runtime flag
 * instead: one game frame per vblank. */
static void nes_wait_vblank(void)
{
    volatile uint8_t *flag = (volatile uint8_t *)NES_VBLANK_FLAG;

    while (*flag == 0u) {
        /* wait for the NMI to begin vblank */
    }
    *flag = 0u;
}

/* Low-level mapper register store. The core mapper code is portable and takes
 * this callback so it can be unit-tested on the PC without NES memory access. */
static void nes_mapper_io_write(uint16_t address, uint8_t value, void *user)
{
    (void)user;
    *((volatile uint8_t *)address) = value;
}

/* cc65 2.19's NMI does not touch $2000 or $2001, so render settings persist
 * once written. */
static void nes_render_enable(void)
{
    PPU.mask = 0x1Eu;
}

static void nes_render_disable(void)
{
    PPU.mask = 0u;
}

/* cc65 exposes a bounded PPU write buffer that its NMI flushes during
 * vblank. Using it keeps large nametable/palette updates off the visible
 * scanlines. This runtime's assembly routine expects A=value, Y=high, X=low. */
static uint8_t g_ppu_value;
static uint8_t g_ppu_high;
static uint8_t g_ppu_low;

static void nes_ppu_write(uint16_t address, uint8_t value)
{
    g_ppu_value = value;
    g_ppu_high = (uint8_t)(address >> 8);
    g_ppu_low = (uint8_t)(address & 0xffu);
    __asm__("lda _g_ppu_value");
    __asm__("ldy _g_ppu_high");
    __asm__("ldx _g_ppu_low");
    __asm__("jsr ppubuf_put");
}

/* Attribute bytes hold one 2-bit palette index per 16x16 tile region. When a
 * background supplies a per-tile palette map, pack four regions into each byte
 * so one nametable can use all four background palettes at once. */
static void nes_write_attributes(const gr_bg *bg, uint16_t attr_base)
{
    uint8_t ax, ay;

    for (ay = 0u; ay < 8u; ++ay) {
        for (ax = 0u; ax < 8u; ++ax) {
            nes_ppu_write((uint16_t)(attr_base + (uint16_t)ay * 8u + ax),
                          gr_bg_attribute(bg, ax, ay));
        }
    }
}

static void nes_upload_background(const gr_bg *bg)
{
    const gr_map *map;
    uint16_t nt_base;
    uint8_t x, y;

    if (bg == NULL || bg->tileset == NULL || bg->map == NULL ||
        bg->map->tiles == NULL) {
        return;
    }
    map = bg->map;
    nt_base = nes_nametable_base(bg->nametable);
    for (y = 0; y < 30u; ++y) {
        uint16_t my = (uint16_t)(y % map->height);
        for (x = 0; x < 32u; ++x) {
            uint16_t mx = (uint16_t)(x % map->width);
            uint16_t index = (uint16_t)(my * map->width + mx);
            nes_ppu_write((uint16_t)(nt_base + (uint16_t)y * 32u + x),
                          (uint8_t)map->tiles[index]);
        }
    }
    nes_write_attributes(bg, (uint16_t)(nt_base + NES_ATTR_OFFSET));
    g_bkg_tileset = bg->tileset;
    g_bkg_source = bg->map;
    g_bg_pal_slot = bg->pal_slot;
    g_bg_nametable = (uint8_t)(bg->nametable & 3u);
    g_bg_palette_map = bg->palette_map;
    g_bg_column = 0xffu;
    g_ppu_ctrl = (uint8_t)(NES_CTRL_BASE | g_bg_nametable);
    *g_ctrl_shadow = g_ppu_ctrl;
}

/* Gramma's custom NMI writes fine scroll to $2005 every vblank. Coarse
 * scrolling is done by rewriting the rightmost nametable column as the map
 * column advances, so only the low three scroll bits belong in the NMI. */
static void nes_update_bg_scroll(const gr_bg *bg)
{
    const gr_map *map;
    uint16_t nt_base;
    uint8_t target, src_x, y;

    if (bg == NULL || bg->map == NULL || bg->map->tiles == NULL) {
        return;
    }
    map = bg->map;
    nt_base = nes_nametable_base(bg->nametable);
    *g_scroll_x = (uint8_t)((uint16_t)(bg->scroll_x >= 0 ? bg->scroll_x : 0) &
                            0x07u);
    *g_scroll_y = (uint8_t)((uint16_t)(bg->scroll_y >= 0 ? bg->scroll_y : 0) &
                            0x07u);
    target = (uint8_t)((bg->scroll_x >= 0 ? bg->scroll_x : 0) / 8);
    if (g_bg_column == 0xffu) {
        g_bg_column = target;
    }
    while (g_bg_column != target) {
        uint8_t old_block = (uint8_t)(g_bg_column >> 2);
        g_bg_column = (uint8_t)(g_bg_column + 1u);
        src_x = (uint8_t)((g_bg_column + 31u) % map->width);
        for (y = 0; y < 30u; ++y) {
            uint8_t src_y = (uint8_t)(y % map->height);
            uint16_t index = (uint16_t)(src_y * map->width + src_x);
            nes_ppu_write((uint16_t)(nt_base + (uint16_t)y * 32u + 31u),
                          (uint8_t)map->tiles[index]);
        }
        /* A split palette map needs fresh attribute bytes every four tiles. */
        if (bg->palette_map != NULL && (g_bg_column >> 2) != old_block) {
            nes_write_attributes(bg, (uint16_t)(nt_base + NES_ATTR_OFFSET));
        }
    }
}

static void nes_write_palette(void)
{
    uint8_t slot, color;

    for (slot = 0; slot < 8u; ++slot) {
        for (color = 0; color < GR_PALETTE_COLORS; ++color) {
            uint8_t value = g_palette[slot][color];
            /* Sprite palette 0 entry 0 mirrors the universal background color. */
            if (slot == 4u && color == 0u) {
                value = g_palette[0][0];
            }
            nes_ppu_write((uint16_t)(NES_PALETTE + (uint16_t)slot * 4u + color),
                          value);
        }
    }
    g_palette_dirty = false;
}

static void nes_write_oam(void)
{
    /* cc65 2.19 has no sprite DMA helper in its NMI. Stage OAM in the last
     * page of the 8 KB work RAM and trigger a hardware DMA during vblank;
     * writing 256 bytes through $2004 is too slow for a 2.19 NMI. */
    memcpy((void *)0x7f00u, g_oam, sizeof(g_oam));
    SPRITE_DMA = 0x7fu;
}

/* The 2C02 palette is an RGB approximation of the NTSC output. Distances are
 * computed against RGB555 so the same converter works for every pipeline
 * output. A few duplicate/glitchy entries are skipped. */
static const uint8_t nes_system_palette[64][3] = {
    { 0x7C, 0x7C, 0x7C }, { 0x00, 0x00, 0xFC }, { 0x00, 0x00, 0xBC },
    { 0x44, 0x28, 0xBC }, { 0x94, 0x00, 0x84 }, { 0xA8, 0x00, 0x20 },
    { 0xA8, 0x10, 0x00 }, { 0x88, 0x14, 0x00 }, { 0x50, 0x30, 0x00 },
    { 0x00, 0x78, 0x00 }, { 0x00, 0x68, 0x00 }, { 0x00, 0x58, 0x00 },
    { 0x00, 0x40, 0x58 }, { 0x00, 0x00, 0x00 }, { 0x00, 0x00, 0x00 },
    { 0x00, 0x00, 0x00 }, { 0xBC, 0xBC, 0xBC }, { 0x00, 0x78, 0xF8 },
    { 0x00, 0x58, 0xF8 }, { 0x68, 0x44, 0xFC }, { 0xD8, 0x00, 0xCC },
    { 0xE4, 0x00, 0x58 }, { 0xF8, 0x38, 0x00 }, { 0xE4, 0x5C, 0x10 },
    { 0xAC, 0x7C, 0x00 }, { 0x00, 0xB8, 0x00 }, { 0x00, 0xA8, 0x00 },
    { 0x00, 0xA8, 0x44 }, { 0x00, 0x88, 0x88 }, { 0x00, 0x00, 0x00 },
    { 0x00, 0x00, 0x00 }, { 0x00, 0x00, 0x00 }, { 0xF8, 0xF8, 0xF8 },
    { 0x3C, 0xBC, 0xFC }, { 0x68, 0x88, 0xFC }, { 0x98, 0x78, 0xF8 },
    { 0xF8, 0x78, 0xF8 }, { 0xF8, 0x58, 0x98 }, { 0xF8, 0x78, 0x58 },
    { 0xFC, 0xA0, 0x44 }, { 0xF8, 0xB8, 0x00 }, { 0xB8, 0xF8, 0x18 },
    { 0x58, 0xD8, 0x54 }, { 0x58, 0xF8, 0x98 }, { 0x00, 0xE8, 0xD8 },
    { 0x78, 0x78, 0x78 }, { 0x00, 0x00, 0x00 }, { 0x00, 0x00, 0x00 },
    { 0xFC, 0xFC, 0xFC }, { 0xA4, 0xE4, 0xFC }, { 0xB8, 0xB8, 0xF8 },
    { 0xD8, 0xB8, 0xF8 }, { 0xF8, 0xB8, 0xF8 }, { 0xF8, 0xA4, 0xC0 },
    { 0xF0, 0xD0, 0xB0 }, { 0xFC, 0xE0, 0xA8 }, { 0xF8, 0xD8, 0x78 },
    { 0xD8, 0xF8, 0x78 }, { 0xB8, 0xF8, 0xB8 }, { 0xB8, 0xF8, 0xD8 },
    { 0x00, 0xFC, 0xFC }, { 0xF8, 0xD8, 0xF8 }, { 0x00, 0x00, 0x00 },
    { 0x00, 0x00, 0x00 }
};

static bool nes_skip_color(uint8_t index)
{
    return index == 0x0du || index == 0x0eu ||
           index == 0x1du || index == 0x1eu || index == 0x1fu ||
           index == 0x2eu || index == 0x2fu ||
           index == 0x3eu || index == 0x3fu;
}

static uint8_t nes_color_index(gr_color color)
{
    uint8_t r = (uint8_t)((color >> 10) & 0x1fu);
    uint8_t g = (uint8_t)((color >> 5) & 0x1fu);
    uint8_t b = (uint8_t)(color & 0x1fu);
    uint8_t best = 0x0fu;
    uint16_t best_distance = 0xffffu;
    uint8_t i;

    for (i = 0; i < 64u; ++i) {
        int16_t dr = (int16_t)r - (int16_t)(nes_system_palette[i][0] >> 3);
        int16_t dg = (int16_t)g - (int16_t)(nes_system_palette[i][1] >> 3);
        int16_t db = (int16_t)b - (int16_t)(nes_system_palette[i][2] >> 3);
        uint16_t distance;

        if (nes_skip_color(i)) {
            continue;
        }
        distance = (uint16_t)(dr * dr * 2 + dg * dg * 4 + db * db);
        if (distance < best_distance) {
            best_distance = distance;
            best = i;
        }
    }
    return best;
}

static void nes_palette_load(uint8_t slot, const gr_color *colors, uint8_t count)
{
    uint8_t i;

    if (slot >= 8u || colors == NULL || count == 0u) {
        return;
    }
    if (count > GR_PALETTE_COLORS) {
        count = GR_PALETTE_COLORS;
    }
    for (i = 0; i < count; ++i) {
        g_palette[slot][i] = nes_color_index(colors[i]);
    }
    while (i < GR_PALETTE_COLORS) {
        g_palette[slot][i++] = 0x0fu;
    }
    g_palette_dirty = true;
}

static void nes_load_tileset_palette(const gr_tileset *tileset, uint8_t slot)
{
    if (slot < 8u && tileset != NULL && tileset->palette != NULL &&
        tileset->palette_size > 0u && g_palette_source[slot] != tileset) {
        nes_palette_load(slot, tileset->palette, tileset->palette_size);
        g_palette_source[slot] = tileset;
    }
}

static void nes_silence(uint8_t channel)
{
    if (channel == 0u) {
        APU.pulse[0].control = 0u;
    } else if (channel == 1u) {
        APU.pulse[1].control = 0u;
    } else if (channel == 2u) {
        APU.triangle.counter = 0u;
    } else {
        APU.noise.control = 0u;
    }
}

static void nes_set_period(uint16_t period, uint8_t *low, uint8_t *high)
{
    if (period > 2047u) {
        period = 2047u;
    }
    *low = (uint8_t)(period & 0xffu);
    *high = (uint8_t)(0xf8u | ((period >> 8) & 0x07u));
}

static void nes_start_tone(uint8_t channel, uint16_t freq, uint8_t volume)
{
    uint16_t period;
    uint8_t low, high;

    if (freq == 0u || volume == 0u) {
        nes_silence(channel);
        return;
    }
    period = (uint16_t)(111860UL / freq);
    if (period > 0u) {
        --period;
    }
    nes_set_period(period, &low, &high);

    if (channel == 0u || channel == 1u) {
        if (channel == 0u) {
            APU.pulse[0].control = (uint8_t)(0x80u | 0x10u |
                                             (volume & 0x0fu));
            APU.pulse[0].ramp = 0u;
            APU.pulse[0].period_low = low;
            APU.pulse[0].len_period_high = high;
        } else {
            APU.pulse[1].control = (uint8_t)(0x80u | 0x10u |
                                             (volume & 0x0fu));
            APU.pulse[1].ramp = 0u;
            APU.pulse[1].period_low = low;
            APU.pulse[1].len_period_high = high;
        }
    } else if (channel == 2u) {
        APU.triangle.counter = 0x80u;
        APU.triangle.period_low = low;
        APU.triangle.len_period_high = high;
    } else {
        APU.noise.control = (uint8_t)(0x10u | (volume & 0x0fu));
        APU.noise.period = (uint8_t)(freq & 0x0fu);
        APU.noise.len = 0xf8u;
    }
}

/* Start a delta-modulated sample. DMC data lives in a 64-byte-aligned ROM
 * segment, so the hardware only needs the CPU address shifted down six bits.
 * $4015 bit 3 is toggled first to abort any sample still playing. */
static void nes_dmc_play(const gr_dmc *dmc)
{
    uint16_t address;

    if (dmc == NULL || dmc->data == NULL || dmc->length < 16u) {
        return;
    }
    address = (uint16_t)(uintptr_t)dmc->data;
    APU.status = 0x07u;         /* keep tones, stop DMC */
    APU.status = 0x0fu;         /* re-enable DMC for the new sample */
    APU.delta_mod.control = (uint8_t)((dmc->rate & 0x0fu) |
                                      (dmc->loop ? 0x10u : 0u) | 0x20u);
    APU.delta_mod.output = 64u;
    APU.delta_mod.address = (uint8_t)(address >> 6);
    APU.delta_mod.length = (uint8_t)((dmc->length >> 4) - 1u);
}

static void nes_play_note(const gr_note *note)
{
    uint8_t channel;

    if (note->freq_hz == 0u || note->volume == 0u) {
        if (g_music_channel != 0xffu) {
            nes_silence(g_music_channel);
        }
        return;
    }
    if (note->wave == GR_WAVE_TRIANGLE) {
        channel = 2u;
    } else if (note->wave == GR_WAVE_NOISE) {
        channel = 3u;
    } else {
        channel = 0u;
    }
    if (g_music_channel != 0xffu && g_music_channel != channel) {
        nes_silence(g_music_channel);
    }
    nes_start_tone(channel, note->freq_hz, note->volume);
    g_music_channel = channel;
}

static void nes_update_audio(void)
{
    const gr_note *note;
    uint16_t frames;

    if (g_sfx_frames > 0u && --g_sfx_frames == 0u) {
        nes_silence(1u);
    }
    if (g_song == NULL || g_song->note_count == 0u || g_song->bpm == 0u) {
        return;
    }
    ++g_note_elapsed_frames;
    note = &g_song->notes[g_note_index];
    frames = (uint16_t)((uint32_t)note->ticks * 60u / g_song->bpm / 4u);
    if (frames == 0u) {
        frames = 1u;
    }
    while (g_note_elapsed_frames >= frames) {
        g_note_elapsed_frames = (uint16_t)(g_note_elapsed_frames - frames);
        ++g_note_index;
        if (g_note_index >= g_song->note_count) {
            if (!g_song->loop) {
                g_song = NULL;
                if (g_music_channel != 0xffu) {
                    nes_silence(g_music_channel);
                }
                return;
            }
            g_note_index = 0u;
        }
        note = &g_song->notes[g_note_index];
        frames = (uint16_t)((uint32_t)note->ticks * 60u / g_song->bpm / 4u);
        if (frames == 0u) {
            frames = 1u;
        }
    }
    if (g_note_index != g_started_index) {
        nes_play_note(note);
        g_started_index = g_note_index;
    }
}

static uint8_t nes_read_pad(uint8_t port)
{
    uint8_t value = 0u;
    uint8_t bit;

    /* The NES joypad is serial: each $4016/$4017 read returns one button,
     * starting with A. Shift them into the canonical Gramma button bitmap. */
    for (bit = 0; bit < 8u; ++bit) {
        if ((JOYPAD[port] & 0x01u) != 0u) {
            value = (uint8_t)(value | (uint8_t)(1u << bit));
        }
    }
    return value;
}

static void nes_read_pads(void)
{
    JOYPAD[0] = 1u;
    JOYPAD[0] = 0u;
    g_raw[0] = nes_read_pad(0u);
    g_raw[1] = nes_read_pad(1u);
}

static void nes_frame_begin(void)
{
    uint8_t p, b;

    nes_read_pads();
    for (p = 0; p < GR_PLAYER_COUNT; ++p) {
        for (b = 0; b < GR_BTN_COUNT; ++b) {
            g_prev[p][b] = g_down[p][b];
            g_down[p][b] = false;
        }
    }
    if (g_cfg == NULL || g_cfg->players == 0u) {
        return;
    }
    g_down[0][GR_BTN_A] = (g_raw[0] & 0x01u) != 0u;
    g_down[0][GR_BTN_B] = (g_raw[0] & 0x02u) != 0u;
    g_down[0][GR_BTN_SELECT] = (g_raw[0] & 0x04u) != 0u;
    g_down[0][GR_BTN_START] = (g_raw[0] & 0x08u) != 0u;
    g_down[0][GR_BTN_UP] = (g_raw[0] & 0x10u) != 0u;
    g_down[0][GR_BTN_DOWN] = (g_raw[0] & 0x20u) != 0u;
    g_down[0][GR_BTN_LEFT] = (g_raw[0] & 0x40u) != 0u;
    g_down[0][GR_BTN_RIGHT] = (g_raw[0] & 0x80u) != 0u;
    if (g_cfg->players > 1u) {
        g_down[1][GR_BTN_A] = (g_raw[1] & 0x01u) != 0u;
        g_down[1][GR_BTN_B] = (g_raw[1] & 0x02u) != 0u;
        g_down[1][GR_BTN_SELECT] = (g_raw[1] & 0x04u) != 0u;
        g_down[1][GR_BTN_START] = (g_raw[1] & 0x08u) != 0u;
        g_down[1][GR_BTN_UP] = (g_raw[1] & 0x10u) != 0u;
        g_down[1][GR_BTN_DOWN] = (g_raw[1] & 0x20u) != 0u;
        g_down[1][GR_BTN_LEFT] = (g_raw[1] & 0x40u) != 0u;
        g_down[1][GR_BTN_RIGHT] = (g_raw[1] & 0x80u) != 0u;
    }
}

static void nes_build_oam(gr_actor *const *actors, uint8_t actor_count)
{
    uint8_t i, used = 0, slot;

    for (slot = 0; slot < NES_MAX_SPRITES; ++slot) {
        g_oam[slot * 4u] = 0xfeu;
    }
    for (i = 0; i < actor_count; ++i) {
        const gr_sprite *s = &actors[i]->sprite;
        uint8_t fw = s->frame_w ? s->frame_w : 1u;
        uint8_t fh = s->frame_h ? s->frame_h : 1u;
        uint8_t ty, tx;
        uint8_t attr;

        if (s->tileset == NULL || !s->visible) {
            continue;
        }
        if (s->tileset != g_sprite_tileset) {
            g_sprite_tileset = s->tileset;
            /* CHR data may span several 8 KB banks. Tile indices are local to
             * one 4 KB pattern table, so wrap the flat ROM offset at 256. */
            g_sprite_tile_base = (uint8_t)(
                ((s->tileset->tiles - nes_chr_data) / 16) & 0xffu);
            nes_load_tileset_palette(s->tileset,
                                     (uint8_t)(4u + (s->pal_slot & 3u)));
        }
        attr = (uint8_t)(s->pal_slot & 3u);
        if ((s->flip & GR_FLIP_X) != 0u) {
            attr |= 0x40u;
        }
        if ((s->flip & GR_FLIP_Y) != 0u) {
            attr |= 0x80u;
        }
        for (ty = 0; ty < fh; ++ty) {
            for (tx = 0; tx < fw; ++tx) {
                int16_t sy = (int16_t)(s->y + (int16_t)(ty * 8u));
                int16_t sx = (int16_t)(s->x + (int16_t)(tx * 8u));

                if (used >= NES_MAX_SPRITES) {
                    return;
                }
                if (sy < 1 || sy > 239 || sx < 0 || sx > 255) {
                    continue;
                }
                {
                    uint8_t tile = (uint8_t)(g_sprite_tile_base +
                                             (uint16_t)s->frame * fw * fh +
                                             (uint16_t)ty * fw + tx);
                    uint8_t *entry = &g_oam[used * 4u];
                    entry[0] = (uint8_t)(sy - 1);
                    entry[1] = tile;
                    entry[2] = attr;
                    entry[3] = (uint8_t)sx;
                    ++used;
                }
            }
        }
    }
}

static void nes_frame_draw(const gr_bg *bg, gr_actor *const *actors,
                           uint8_t actor_count)
{
    if (bg != NULL && bg->tileset != NULL && bg->map != NULL) {
        g_current_bg = bg;
        if (bg->tileset != g_bkg_tileset || bg->map != g_bkg_source ||
            bg->pal_slot != g_bg_pal_slot ||
            (uint8_t)(bg->nametable & 3u) != g_bg_nametable ||
            bg->palette_map != g_bg_palette_map) {
            g_pending_bg = bg;
            g_bg_upload_pending = true;
        }
        nes_load_tileset_palette(bg->tileset, bg->pal_slot & 3u);
    }
    nes_build_oam(actors, actor_count);
}

static void nes_frame_end(void)
{
    nes_wait_vblank();
    g_overlay_writes = 0u;
    (void)gr_overlay_flush();
    nes_write_oam();

    if (g_bg_upload_pending) {
        nes_upload_background(g_pending_bg);
        g_bg_upload_pending = false;
        g_pending_bg = NULL;
    }
    if (g_palette_dirty) {
        nes_write_palette();
    }
    if (g_current_bg != NULL) {
        nes_update_bg_scroll(g_current_bg);
    }
    /* This runtime's NMI leaves $2000/$2001 alone, so these persist. */
    PPU.control = g_ppu_ctrl;
    nes_render_enable();
    nes_update_audio();
}

static bool nes_pad_down(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return g_down[player][button];
}

static bool nes_pad_pressed(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return g_down[player][button] && !g_prev[player][button];
}

static bool nes_pad_released(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return !g_down[player][button] && g_prev[player][button];
}

static gr_result nes_music_play(const gr_song *song)
{
    g_song = song;
    g_note_index = 0u;
    g_started_index = 0xffffu;
    g_note_elapsed_frames = 0u;
    if (g_music_channel != 0xffu) {
        nes_silence(g_music_channel);
        g_music_channel = 0xffu;
    }
    if (song != NULL && song->note_count > 0u) {
        nes_play_note(&song->notes[0]);
        g_started_index = 0u;
    }
    return GR_OK;
}

static void nes_music_stop(void)
{
    g_song = NULL;
    if (g_music_channel != 0xffu) {
        nes_silence(g_music_channel);
        g_music_channel = 0xffu;
    }
}

static void nes_sfx_play(uint16_t id, uint8_t channel)
{
    const gr_sfx_def *def;
    uint16_t freq;

    (void)channel;
    if (g_cfg == NULL || id >= g_cfg->sfx_count) {
        return;
    }
    def = g_cfg->sfx[id];
    if (def->dmc != NULL) {
        /* PCM WAV assets carry a 4-bit DMC twin generated by the pipeline. */
        g_sfx_frames = 0u;
        nes_dmc_play(def->dmc);
        return;
    }
    freq = def->freq_hz;
    if (freq == 0u) {
        freq = 220u;            /* PCM-only asset without a DMC twin */
    }
    nes_start_tone(1u, freq, def->volume);
    g_sfx_frames = (uint16_t)(def->duration_ms / 17u);
    if (g_sfx_frames == 0u) {
        g_sfx_frames = 1u;
    }
}

static uint32_t nes_ticks(void)
{
    static uint32_t counter;
    return ++counter * 17u;
}

static bool nes_quit_requested(void)
{
    return false;
}

static gr_result nes_init(const gr_config *cfg)
{
    uint8_t slot, color;

    g_cfg = cfg;
    /* The crt0 already programmed the mapper; this installs the same state in
     * C so games can switch banks at runtime through gr_nes_mapper_*_banks(). */
    (void)gr_nes_mapper_runtime_init_layout((gr_nes_mapper)gr_nes_mapper_id,
                                            gr_nes_prg_banks,
                                            nes_mapper_io_write, NULL);
    g_bkg_tileset = NULL;
    g_bkg_source = NULL;
    g_current_bg = NULL;
    g_pending_bg = NULL;
    g_bg_upload_pending = false;
    g_bg_column = 0xffu;
    g_bg_pal_slot = 0xffu;
    g_bg_nametable = 0xffu;
    g_bg_palette_map = NULL;
    g_sprite_tileset = NULL;
    g_sprite_tile_base = 0u;
    g_song = NULL;
    g_sfx_frames = 0u;
    g_music_channel = 0xffu;
    g_note_index = 0u;
    g_started_index = 0xffffu;
    g_note_elapsed_frames = 0u;
    memset(g_down, 0, sizeof(g_down));
    memset(g_prev, 0, sizeof(g_prev));
    memset(g_raw, 0, sizeof(g_raw));
    memset(g_oam, 0xfe, sizeof(g_oam));

    for (slot = 0; slot < 8u; ++slot) {
        g_palette_source[slot] = NULL;
        for (color = 0; color < GR_PALETTE_COLORS; ++color) {
            g_palette[slot][color] = 0x0fu;
        }
    }
    g_palette_dirty = true;

    nes_render_disable();
    APU.status = 0x0fu;
    APU.fcontrol = 0u;
    *g_ctrl_shadow = g_ppu_ctrl;
    PPU.control = g_ppu_ctrl;
    nes_render_enable();
    return GR_OK;
}

static void nes_quit(void)
{
    nes_render_disable();
    g_ppu_ctrl = 0u;
    PPU.control = 0u;
    APU.status = 0u;
    g_song = NULL;
    g_cfg = NULL;
}

/* Read data from a 16 KB PRG bank into RAM. The routine is linked into the
 * RAMCODE segment and copied there by nes_crt0.s, because switching MMC3 R6 or
 * MMC1's PRG window would otherwise swap out the caller. Interrupts are paused
 * via PPUCTRL bit 7 so the shared NMI cannot race the mapper registers. */
#if defined(GRAMMA_TARGET_NES) && defined(GR_NES_RAMCODE)
#pragma code-name(push, "RAMCODE")
gr_result gr_nes_prg_read(uint8_t prg_bank, uint16_t offset,
                          uint8_t *dst, uint16_t length)
{
    gr_nes_mapper id = gr_nes_mapper_runtime_id();
    uint16_t saved = gr_bank_current(gr_nes_mapper_prg_banks(), 0u);
    uint8_t control = g_ppu_ctrl;
    uint8_t window;
    uint8_t bit;
    uint16_t chunk;
    uint16_t limit;
    const uint8_t *src;
    volatile uint8_t *reg;

    if (dst == NULL || prg_bank >= gr_nes_prg_banks ||
        (id != GR_NES_MAPPER_MMC1 && id != GR_NES_MAPPER_MMC3)) {
        return GR_ERR_INVALID_ARG;
    }

    PPU.control = (uint8_t)(control & 0x7fu);
    while (length != 0u) {
        if (id == GR_NES_MAPPER_MMC1) {
            window = prg_bank;
            src = (const uint8_t *)(0x8000u + offset);
            limit = 0x4000u - offset;
            reg = (volatile uint8_t *)0xa000u;
            *reg = 0x80u;
            for (bit = 0u; bit < 5u; ++bit) {
                *reg = (uint8_t)((window >> bit) & 1u);
            }
        } else {
            window = (uint8_t)((prg_bank << 1) | (uint8_t)(offset >> 13));
            src = (const uint8_t *)(0x8000u + (offset & 0x1fffu));
            limit = 0x2000u - (offset & 0x1fffu);
            *((volatile uint8_t *)0x8000u) = 0x86u;
            *((volatile uint8_t *)0x8001u) = window;
        }
        chunk = length < limit ? length : limit;
        while (chunk != 0u) {
            *dst++ = *src++;
            --chunk;
            --length;
        }
        offset = (uint16_t)(offset + limit);
        if (id == GR_NES_MAPPER_MMC3) {
            offset = (uint16_t)(offset & 0x3fffu);
        }
    }

    if (id == GR_NES_MAPPER_MMC1) {
        reg = (volatile uint8_t *)0xa000u;
        *reg = 0x80u;
        for (bit = 0u; bit < 5u; ++bit) {
            *reg = (uint8_t)((saved >> bit) & 1u);
        }
    } else {
        *((volatile uint8_t *)0x8000u) = 0x86u;
        *((volatile uint8_t *)0x8001u) = (uint8_t)saved;
    }
    PPU.control = control;
    g_ppu_ctrl = control;
    return GR_OK;
}
#pragma code-name(pop)
#endif

/* CHR lives in ROM on every supported mapper, so tile overlays are expressed
 * as bank switches plus nametable patches rather than pattern-table uploads. */
static gr_result nes_overlay_tiles(uint8_t dest, const uint8_t *data,
                                   uint16_t count, bool sprite)
{
    (void)dest;
    (void)data;
    (void)count;
    (void)sprite;
    return GR_ERR_UNSUPPORTED;
}

static gr_result nes_overlay_nametable(uint8_t x, uint8_t y, uint8_t w,
                                       uint8_t h, const uint8_t *tiles)
{
    uint8_t row, col;
    uint16_t nt_base;

    if (x + w > 32u || y + h > 30u) {
        return GR_ERR_INVALID_ARG;
    }
    nt_base = nes_nametable_base(g_bg_nametable == 0xffu ? 0u
                                                         : g_bg_nametable);
    if ((uint16_t)g_overlay_writes + (uint16_t)w * (uint16_t)h >
        NES_OVERLAY_VBLANK_BUDGET) {
        return GR_ERR_NO_MEMORY;
    }
    g_overlay_writes = (uint8_t)(g_overlay_writes + (uint8_t)((uint16_t)w *
                                                              (uint16_t)h));
    for (row = 0u; row < h; ++row) {
        for (col = 0u; col < w; ++col) {
            uint16_t index = (uint16_t)row * (uint16_t)w + (uint16_t)col;
            nes_ppu_write((uint16_t)(nt_base +
                (uint16_t)(y + row) * 32u + (uint16_t)(x + col)),
                tiles[index]);
        }
    }
    return GR_OK;
}

const gr_backend gr_backend_nes = {
    "nes",
    { GR_BUTTON_BIT(GR_BTN_UP) | GR_BUTTON_BIT(GR_BTN_DOWN) |
      GR_BUTTON_BIT(GR_BTN_LEFT) | GR_BUTTON_BIT(GR_BTN_RIGHT) |
      GR_BUTTON_BIT(GR_BTN_A) | GR_BUTTON_BIT(GR_BTN_B) |
      GR_BUTTON_BIT(GR_BTN_START) | GR_BUTTON_BIT(GR_BTN_SELECT),
      GR_BUTTON_BIT(GR_BTN_UP) | GR_BUTTON_BIT(GR_BTN_DOWN) |
      GR_BUTTON_BIT(GR_BTN_LEFT) | GR_BUTTON_BIT(GR_BTN_RIGHT) |
      GR_BUTTON_BIT(GR_BTN_A) | GR_BUTTON_BIT(GR_BTN_B) |
      GR_BUTTON_BIT(GR_BTN_START) | GR_BUTTON_BIT(GR_BTN_SELECT) },
    nes_init,
    nes_quit,
    nes_frame_begin,
    nes_frame_draw,
    nes_frame_end,
    nes_pad_down,
    nes_pad_pressed,
    nes_pad_released,
    nes_palette_load,
    nes_music_play,
    nes_music_stop,
    nes_sfx_play,
    nes_ticks,
    nes_quit_requested,
    nes_overlay_tiles,
    nes_overlay_nametable
};
