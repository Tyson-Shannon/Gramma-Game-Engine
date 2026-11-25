/* Optional per-target capability queries. These live in the portable core so
 * every build driver picks them up from the core source list; the functions fail
 * explicitly when a game includes the wrong target header in a build. */

#include <gramma/target/gb/system.h>
#include <gramma/target/nes/system.h>
#include <gramma/target/sms/system.h>

gr_result gr_gb_system_query(gr_gb_system_caps *out)
{
#if defined(GRAMMA_TARGET_GB)
    if (out == 0) {
        return GR_ERR_INVALID_ARG;
    }
    out->tile_bytes = GR_GB_TILE_BYTES;
    out->bpp = GR_GB_TILE_BPP;
    out->palette_colors = GR_GB_PALETTE_COLORS;
    out->palette_slots = GR_GB_PALETTE_SLOTS;
    out->players = GR_GB_PLAYERS;
    out->screen_w = GR_GB_SCREEN_W;
    out->screen_h = GR_GB_SCREEN_H;
    out->name = "Game Boy";
    return GR_OK;
#else
    (void)out;
    return GR_ERR_UNSUPPORTED;
#endif
}

gr_result gr_nes_system_query(gr_nes_system_caps *out)
{
#if defined(GRAMMA_TARGET_NES)
    if (out == 0) {
        return GR_ERR_INVALID_ARG;
    }
    out->tile_bytes = GR_NES_TILE_BYTES;
    out->bpp = GR_NES_TILE_BPP;
    out->palette_colors = GR_NES_PALETTE_COLORS;
    out->palette_slots = GR_NES_PALETTE_SLOTS;
    out->players = GR_NES_PLAYERS;
    out->screen_w = GR_NES_SCREEN_W;
    out->screen_h = GR_NES_SCREEN_H;
    out->nametable_w = GR_NES_NAMETABLE_W;
    out->nametable_h = GR_NES_NAMETABLE_H;
    out->name = "NES";
    return GR_OK;
#else
    (void)out;
    return GR_ERR_UNSUPPORTED;
#endif
}

gr_result gr_sms_system_query(gr_sms_system_caps *out)
{
#if defined(GRAMMA_TARGET_SMS)
    if (out == 0) {
        return GR_ERR_INVALID_ARG;
    }
    out->tile_bytes = GR_SMS_TILE_BYTES;
    out->bpp = GR_SMS_TILE_BPP;
    out->palette_colors = GR_SMS_PALETTE_COLORS;
    out->palette_slots = GR_SMS_PALETTE_SLOTS;
    out->players = GR_SMS_PLAYERS;
    out->screen_w = GR_SMS_SCREEN_W;
    out->screen_h = GR_SMS_SCREEN_H;
    out->sprite_tile_base = GR_SMS_SPRITE_TILE_BASE;
    out->name = "SMS/Game Gear";
    return GR_OK;
#else
    (void)out;
    return GR_ERR_UNSUPPORTED;
#endif
}
