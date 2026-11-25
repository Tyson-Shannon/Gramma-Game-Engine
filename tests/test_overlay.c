#include <gramma/overlay.h>
#include <assert.h>

static void test_queue_and_flush(void)
{
    uint8_t tiles[32];
    uint8_t names[8];
    uint8_t i;

    for (i = 0u; i < sizeof(tiles); ++i) {
        tiles[i] = (uint8_t)(i + 1u);
    }
    for (i = 0u; i < sizeof(names); ++i) {
        names[i] = (uint8_t)(i + 2u);
    }

    gr_overlay_clear();
    assert(gr_overlay_pending() == 0u);
    assert(gr_overlay_tiles(64u, tiles, sizeof(tiles), true) == GR_OK);
    assert(gr_overlay_nametable(2u, 3u, 4u, 2u, names) == GR_OK);
    assert(gr_overlay_pending() == 2u);
    assert(gr_overlay_flush() == GR_OK);
    assert(gr_overlay_pending() == 0u);
}

static void test_queue_limits(void)
{
    uint8_t big[GR_OVERLAY_TILE_BYTES];
    uint8_t tile[16];
    uint16_t i;

    for (i = 0u; i < GR_OVERLAY_TILE_BYTES; ++i) {
        big[i] = 0xa5u;
        tile[i & 0x0fu] = 0x5au;
    }
    gr_overlay_clear();
    assert(gr_overlay_tiles(0u, big, sizeof(big), false) == GR_OK);
    assert(gr_overlay_tiles(16u, tile, sizeof(tile), false) ==
           GR_ERR_NO_MEMORY);
    assert(gr_overlay_tiles(0u, NULL, sizeof(tile), false) ==
           GR_ERR_NO_MEMORY);

    gr_overlay_clear();
    for (i = 0u; i < GR_OVERLAY_MAX_OPS; ++i) {
        assert(gr_overlay_tiles((uint8_t)(i * 16u), tile,
                                sizeof(tile), false) == GR_OK);
    }
    assert(gr_overlay_tiles(0u, tile, sizeof(tile), false) ==
           GR_ERR_NO_MEMORY);
    assert(gr_overlay_nametable(0u, 0u, 0u, 1u, tile) ==
           GR_ERR_INVALID_ARG);
    gr_overlay_clear();
}

int main(void)
{
    test_queue_and_flush();
    test_queue_limits();
    return 0;
}
