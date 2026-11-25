#include <assert.h>
#include <gramma/target/gb/system.h>
#include <gramma/target/nes/system.h>
#include <gramma/target/sms/system.h>

int main(void)
{
    gr_gb_system_caps gb;
    gr_nes_system_caps nes;
    gr_sms_system_caps sms;

    assert(GR_GB_TILE_BYTES == 16u);
    assert(GR_NES_TILE_BYTES == 16u);
    assert(GR_SMS_TILE_BYTES == 32u);

    if (gr_gb_system_query(&gb) == GR_OK) {
        assert(gb.tile_bytes == GR_GB_TILE_BYTES);
        assert(gb.players == GR_GB_PLAYERS);
        assert(gb.screen_w == GR_GB_SCREEN_W);
    } else {
        assert(gr_gb_system_query(&gb) == GR_ERR_UNSUPPORTED);
    }
    if (gr_nes_system_query(&nes) == GR_OK) {
        assert(nes.nametable_w == GR_NES_NAMETABLE_W);
        assert(nes.palette_colors == GR_NES_PALETTE_COLORS);
    } else {
        assert(gr_nes_system_query(&nes) == GR_ERR_UNSUPPORTED);
    }
    if (gr_sms_system_query(&sms) == GR_OK) {
        assert(sms.sprite_tile_base == GR_SMS_SPRITE_TILE_BASE);
        assert(sms.bpp == GR_SMS_TILE_BPP);
    } else {
        assert(gr_sms_system_query(&sms) == GR_ERR_UNSUPPORTED);
    }
    assert(gr_gb_system_query(0) != GR_OK);
    return 0;
}
