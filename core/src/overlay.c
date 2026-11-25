#include <gramma/overlay.h>
#include <gramma/internal/backend.h>
#include <string.h>

/* Small staging queue shared by all backends. Source bytes are copied when an
 * operation is queued, so a game can restore a banked ROM window immediately
 * and still have the overlay applied in the next vblank. */

#define GR_OVERLAY_OP_TILES     0u
#define GR_OVERLAY_OP_NAMETABLE 1u

typedef struct {
    uint8_t  kind;
    uint8_t  dest;
    uint8_t  x;
    uint8_t  y;
    uint8_t  w;
    uint8_t  h;
    uint8_t  sprite;
    uint16_t offset;
    uint16_t count;
} gr_overlay_op;

static gr_overlay_op g_ops[GR_OVERLAY_MAX_OPS];
static uint8_t g_tile_data[GR_OVERLAY_TILE_BYTES];
static uint8_t g_map_data[GR_OVERLAY_MAP_BYTES];
static uint16_t g_tile_used;
static uint16_t g_map_used;
static uint8_t g_op_count;

void gr_overlay_clear(void)
{
    g_op_count = 0u;
    g_tile_used = 0u;
    g_map_used = 0u;
}

uint8_t gr_overlay_pending(void)
{
    return g_op_count;
}

static bool overlay_can_queue(uint16_t tile_bytes, uint16_t map_bytes)
{
    return g_op_count < GR_OVERLAY_MAX_OPS &&
           (uint16_t)(g_tile_used + tile_bytes) <= GR_OVERLAY_TILE_BYTES &&
           (uint16_t)(g_map_used + map_bytes) <= GR_OVERLAY_MAP_BYTES;
}

gr_result gr_overlay_tiles(uint8_t dest, const uint8_t *src, uint16_t bytes,
                           bool sprite)
{
    gr_overlay_op *op;

    if (src == NULL || bytes == 0u ||
        !overlay_can_queue(bytes, 0u)) {
        return GR_ERR_NO_MEMORY;
    }
    op = &g_ops[g_op_count];
    op->kind = GR_OVERLAY_OP_TILES;
    op->dest = dest;
    op->offset = g_tile_used;
    op->count = bytes;
    op->sprite = sprite ? 1u : 0u;
    op->x = 0u;
    op->y = 0u;
    op->w = 0u;
    op->h = 0u;
    memcpy(g_tile_data + g_tile_used, src, bytes);
    g_tile_used = (uint16_t)(g_tile_used + bytes);
    ++g_op_count;
    return GR_OK;
}

gr_result gr_overlay_nametable(uint8_t x, uint8_t y, uint8_t w, uint8_t h,
                               const uint8_t *tiles)
{
    uint16_t bytes;
    gr_overlay_op *op;

    if (tiles == NULL || w == 0u || h == 0u) {
        return GR_ERR_INVALID_ARG;
    }
    bytes = (uint16_t)w * (uint16_t)h;
    if (!overlay_can_queue(0u, bytes)) {
        return GR_ERR_NO_MEMORY;
    }
    op = &g_ops[g_op_count];
    op->kind = GR_OVERLAY_OP_NAMETABLE;
    op->dest = 0u;
    op->x = x;
    op->y = y;
    op->w = w;
    op->h = h;
    op->sprite = 0u;
    op->offset = g_map_used;
    op->count = bytes;
    memcpy(g_map_data + g_map_used, tiles, bytes);
    g_map_used = (uint16_t)(g_map_used + bytes);
    ++g_op_count;
    return GR_OK;
}

gr_result gr_overlay_flush(void)
{
    const gr_backend *backend = gr_backend_get();
    gr_result result = GR_OK;
    uint8_t i;

    if (backend == NULL || g_op_count == 0u) {
        gr_overlay_clear();
        return GR_OK;
    }
    for (i = 0u; i < g_op_count; ++i) {
        gr_overlay_op *op = &g_ops[i];
        gr_result step;

        if (op->kind == GR_OVERLAY_OP_TILES) {
            if (backend->overlay_tiles == NULL) {
                step = GR_ERR_UNSUPPORTED;
            } else {
                step = backend->overlay_tiles(op->dest,
                    g_tile_data + op->offset, op->count, op->sprite != 0u);
            }
        } else {
            if (backend->overlay_nametable == NULL) {
                step = GR_ERR_UNSUPPORTED;
            } else {
                step = backend->overlay_nametable(op->x, op->y, op->w, op->h,
                    g_map_data + op->offset);
            }
        }
        if (step != GR_OK && result == GR_OK) {
            result = step;
        }
    }
    gr_overlay_clear();
    return result;
}
