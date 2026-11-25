#include "chr_switch.h"

#include <gramma/gramma.h>
#include <gramma/bank.h>

#if defined(GRAMMA_TARGET_NES)
#include <gramma/target/nes/mapper.h>

/* MMC3 slot 2 selects the 4 KB sprite pattern table. Asset banks are 8 KB,
 * mirrored into two identical 4 KB halves. */
#define CHR_SWITCH_SLOT 2u
static gr_bank_switch g_switch;
#elif defined(GRAMMA_TARGET_GB)
#include <gramma/overlay.h>
#include <gramma/target/gb/mapper.h>

#define GB_SPRITE_TILE_BASE 64u

extern const gr_tileset kart_tileset;
extern const gr_tileset altkart_tileset;
#if GR_GB_ROM_BANKS > 2u
#include "gb/gb_bank_probe.h"
#endif

static const uint8_t g_patch_normal[8] = {
    0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u
};
static const uint8_t g_patch_alternate[8] = {
    2u, 2u, 2u, 2u, 2u, 2u, 2u, 2u
};
#elif defined(GRAMMA_TARGET_SMS)
#include <gramma/overlay.h>
#include <gramma/target/sms/mapper.h>

/* SMS sprites use VRAM tiles 256..511; 4bpp tiles are 32 bytes each. */
#define SMS_SPRITE_TILE_BASE 256u

extern const gr_tileset kart_tileset;
extern const gr_tileset altkart_tileset;
#if GR_SMS_ROM_BANKS > 2u
#include "sms/sms_bank_probe.h"
#endif

static const uint8_t g_patch_normal[8] = {
    0u, 0u, 0u, 0u, 0u, 0u, 0u, 0u
};
static const uint8_t g_patch_alternate[8] = {
    2u, 2u, 2u, 2u, 2u, 2u, 2u, 2u
};
#endif

static bool g_ready;
static bool g_probe_ok;
static bool g_alternate;
static bool g_prev_b;

void chr_switch_init(void) GR_CHR_SWITCH_FIXED
{
    g_prev_b = false;
    g_ready = false;
    g_probe_ok = false;
    g_alternate = false;
#if defined(GRAMMA_TARGET_NES)
    g_ready = gr_nes_mapper_runtime_id() == GR_NES_MAPPER_MMC3 &&
              gr_bank_slots(gr_nes_mapper_chr_banks()) > CHR_SWITCH_SLOT &&
              gr_bank_switch_init(&g_switch, gr_nes_mapper_chr_banks(),
                                  CHR_SWITCH_SLOT, GR_NES_CHR_BANK4(0),
                                  GR_NES_CHR_BANK4(1)) == GR_OK;
#elif defined(GRAMMA_TARGET_GB)
#if GR_GB_ROM_BANKS > 2u
    if (gr_gb_mapper_runtime_id() != GR_GB_MAPPER_NONE &&
        gr_gb_mapper_rom_bank_count() > 2u &&
        gr_bank_slots(gr_gb_mapper_rom_banks()) > 0u) {
        uint8_t probe;

        g_ready = true;
        /* The generic bank set's function-pointer trampoline lives in bank 1,
         * so it cannot be used once the window changes. GBDK's BANKED helper
         * saves/restores bank 1 around the switch from fixed code. */
        probe = gb_bank_probe_read();
        g_probe_ok = probe == 0x5au;
    }
#endif
#elif defined(GRAMMA_TARGET_SMS)
    /* The overlay toggle works on every SMS ROM; banked art is extra. */
    g_ready = true;
#if GR_SMS_ROM_BANKS > 2u
    if (gr_sms_mapper_rom_bank_count() > 2u &&
        gr_bank_slots(gr_sms_mapper_rom_banks()) > 0u) {
        g_probe_ok = sms_bank_probe_read() == 0x5au;
    }
#endif
#endif
}

bool chr_switch_probe_ok(void)
{
    return g_probe_ok;
}

void chr_switch_update(void)
{
    bool down = gr_pad_down(GR_PLAYER_1, GR_BTN_B);

    if (down && !g_prev_b && g_ready) {
#if defined(GRAMMA_TARGET_NES)
        (void)gr_bank_switch_toggle(&g_switch);
#elif defined(GRAMMA_TARGET_GB)
        const gr_tileset *tiles;
        uint16_t bytes;

        g_alternate = !g_alternate;
        tiles = g_alternate ? &altkart_tileset : &kart_tileset;
        bytes = (uint16_t)tiles->tile_count * 16u;
        /* Both operations are copied into the overlay queue now and applied in
         * the backend's vblank handler, so sprites and map change together. */
        (void)gr_overlay_tiles(GB_SPRITE_TILE_BASE, tiles->tiles, bytes, true);
        (void)gr_overlay_nametable(0u, 0u, 4u, 2u,
                                   g_alternate ? g_patch_alternate
                                               : g_patch_normal);
#elif defined(GRAMMA_TARGET_SMS)
        const gr_tileset *tiles;
        uint16_t bytes;

        g_alternate = !g_alternate;
        tiles = g_alternate ? &altkart_tileset : &kart_tileset;
        bytes = (uint16_t)tiles->tile_count * 32u;
        (void)gr_overlay_tiles(SMS_SPRITE_TILE_BASE, tiles->tiles, bytes, true);
        (void)gr_overlay_nametable(0u, 0u, 4u, 2u,
                                   g_alternate ? g_patch_alternate
                                               : g_patch_normal);
#endif
    }
    g_prev_b = down;
}
