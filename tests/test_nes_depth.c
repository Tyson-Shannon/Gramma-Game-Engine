/* Host-side checks for the portable half of the NES depth features. */
#include <gramma/gramma.h>
#include <assert.h>

static void test_bg_defaults_and_setters(void)
{
    gr_bg bg;
    gr_tileset tileset;
    gr_map map;
    uint16_t tile = 0u;
    gr_color palette[4] = { 0u, 1u, 2u, 3u };
    uint8_t i;

    tileset.tile_count = 1u;
    tileset.bpp = 2u;
    tileset.tiles = (const uint8_t *)&tile;
    tileset.palette = palette;
    tileset.palette_size = 4u;
    map.width = 8u;
    map.height = 8u;
    map.tiles = &tile;

    gr_bg_init(&bg, &tileset, &map, 2u);
    assert(bg.nametable == 0u);
    assert(bg.palette_map == NULL);
    assert(gr_bg_attribute(&bg, 0u, 0u) == 0xaau); /* slot 2 everywhere */

    /* Out-of-range nametables wrap to two bits, matching the PPU register. */
    gr_bg_set_nametable(&bg, 7u);
    assert(bg.nametable == 3u);
    gr_bg_set_nametable(&bg, 0u);

    /* Four regions of one attribute byte: TL=0, TR=1, BL=2, BR=3. */
    {
        uint8_t slots[64];
        for (i = 0u; i < 64u; ++i) {
            slots[i] = 0u;
        }
        slots[0u] = 0u;   /* top left */
        slots[2u] = 1u;   /* top right */
        slots[16u] = 2u;  /* bottom left */
        slots[18u] = 3u;  /* bottom right */
        gr_bg_set_palette_map(&bg, slots);
        assert(gr_bg_attribute(&bg, 0u, 0u) == 0xe4u);
        assert(gr_bg_attribute(&bg, 1u, 0u) == 0x00u);
        assert(bg.palette_map == slots);
        gr_bg_set_palette_map(&bg, NULL);
        assert(gr_bg_attribute(&bg, 0u, 0u) == 0xaau);
    }
    assert(gr_bg_attribute(&bg, 8u, 0u) == 0u);
    assert(gr_bg_attribute(NULL, 0u, 0u) == 0u);
}

static void test_pcm_dmc_descriptor(void)
{
    static const int8_t pcm_data[1] = { 0 };
    static const uint8_t dmc_data[16] = { 0 };
    static const gr_pcm pcm = { 22050u, 1u, pcm_data };
    static const gr_dmc dmc = { 15u, 16u, dmc_data, true };
    static const gr_sfx_def sfx = {
        GR_WAVE_PCM, 0u, 0, 16u, 15u, &pcm, &dmc
    };

    assert(sfx.wave == GR_WAVE_PCM);
    assert(sfx.pcm == &pcm);
    assert(sfx.dmc == &dmc);
    assert(sfx.dmc->rate == 15u);
    assert(sfx.dmc->length == 16u);
    assert(sfx.dmc->loop);
}

int main(void)
{
    test_bg_defaults_and_setters();
    test_pcm_dmc_descriptor();
    return 0;
}
