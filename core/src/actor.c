#include <gramma/gramma.h>
#include <gramma/internal/actor_list.h>
#include <string.h>

/* Static pool: no malloc, ever.  Slots are reused after gr_actor_destroy. */

typedef struct {
    gr_actor items[GR_MAX_ACTORS];
    uint8_t  high_water;
    uint8_t  limit;
} ActorPool;

static ActorPool g_pool;

void gr_actor_set_limit(uint8_t limit)
{
    g_pool.limit = limit;
}

void gr_actor_clear(void)
{
    memset(g_pool.items, 0, sizeof(g_pool.items));
    g_pool.high_water = 0;
}

gr_actor *gr_actor_spawn(const gr_actor_def *def)
{
    uint8_t i;
    gr_actor *a;

    if (def == NULL || def->tileset == NULL) {
        return NULL;
    }
    for (i = 0; i < g_pool.high_water; ++i) {
        if (!g_pool.items[i].alive) {
            break;
        }
    }
    if (i >= g_pool.limit || i >= GR_MAX_ACTORS) {
        return NULL;
    }
    if (i == g_pool.high_water) {
        ++g_pool.high_water;
    }

    a = &g_pool.items[i];
    memset(a, 0, sizeof(*a));
    a->id = i;
    a->alive = true;
    a->x = def->x;
    a->y = def->y;
    a->vx = def->vx;
    a->vy = def->vy;
    a->update = def->update;
    a->userdata = def->userdata;

    a->sprite.tileset = def->tileset;
    a->sprite.pal_slot = def->pal_slot;
    a->sprite.frame_w = def->frame_w ? def->frame_w : 2;
    a->sprite.frame_h = def->frame_h ? def->frame_h : 2;
    a->sprite.frame = def->frame;
    a->sprite.visible = true;
    a->sprite.x = gr_ftoi(a->x);
    a->sprite.y = gr_ftoi(a->y);
    return a;
}

void gr_actor_destroy(gr_actor *actor)
{
    if (actor != NULL && actor->alive) {
        actor->alive = false;
        actor->sprite.visible = false;
    }
}

uint8_t gr_actor_count(void)
{
    uint8_t i, n = 0;
    for (i = 0; i < g_pool.high_water; ++i) {
        if (g_pool.items[i].alive) {
            ++n;
        }
    }
    return n;
}

void gr_actor_update_all(gr_fixed dt)
{
    uint8_t i;
    for (i = 0; i < g_pool.high_water; ++i) {
        gr_actor *a = &g_pool.items[i];
        if (!a->alive) {
            continue;
        }
        if (a->update != NULL) {
            a->update(a, dt);
        }
        a->x += gr_fmul(a->vx, dt);
        a->y += gr_fmul(a->vy, dt);
        a->sprite.x = gr_ftoi(a->x);
        a->sprite.y = gr_ftoi(a->y);
    }
}

/* Called by gr_draw_frame in api.c. */
uint8_t gr_actor_list(gr_actor **out, uint8_t capacity)
{
    uint8_t i, n = 0;
    for (i = 0; i < g_pool.high_water && n < capacity; ++i) {
        if (g_pool.items[i].alive && g_pool.items[i].sprite.visible) {
            out[n++] = &g_pool.items[i];
        }
    }
    return n;
}
