#include <SDL2/SDL.h>
#include <gramma/gramma.h>
#include <gramma/internal/backend.h>
#include <gramma/overlay.h>
#include "pc_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* PC simulator backend: SDL2 window, software tile renderer, keyboard and
   gamepad input. Intended to be the fastest inner loop, not a shippable target. */

typedef struct {
    SDL_Window        *window;
    SDL_Renderer      *renderer;
    SDL_Texture       *texture;
    uint16_t          *fb;
    int                width;
    int                height;
    int                scale;
    uint32_t           start_tick;
    uint32_t           last_frame_tick;
    uint32_t           frame_number;
    uint32_t           test_frames;
    bool               quit;
    char               screenshot[260];
    bool               down[GR_PLAYER_COUNT][GR_BTN_COUNT];
    bool               prev[GR_PLAYER_COUNT][GR_BTN_COUNT];
    SDL_GameController *controllers[GR_PLAYER_COUNT];
    gr_color           palettes[GR_MAX_PALETTES][GR_PALETTE_COLORS];
    bool               palette_used[GR_MAX_PALETTES];
    const gr_config    *cfg;
} PCState;

static PCState g_pc;

static const SDL_Scancode keys[GR_PLAYER_COUNT][GR_BTN_COUNT] = {
    {
        SDL_SCANCODE_UP, SDL_SCANCODE_DOWN, SDL_SCANCODE_LEFT,
        SDL_SCANCODE_RIGHT, SDL_SCANCODE_Z, SDL_SCANCODE_X,
        SDL_SCANCODE_C, SDL_SCANCODE_V, SDL_SCANCODE_LSHIFT,
        SDL_SCANCODE_LCTRL, SDL_SCANCODE_RETURN, SDL_SCANCODE_BACKSPACE
    },
    {
        SDL_SCANCODE_W, SDL_SCANCODE_S, SDL_SCANCODE_A,
        SDL_SCANCODE_D, SDL_SCANCODE_J, SDL_SCANCODE_K,
        SDL_SCANCODE_U, SDL_SCANCODE_I, SDL_SCANCODE_O,
        SDL_SCANCODE_P, SDL_SCANCODE_TAB, SDL_SCANCODE_GRAVE
    }
};

static void pc_quit(void);
static gr_result pc_init(const gr_config *cfg)
{
    int scale = 3;
    const char *scale_env = getenv("GRAMMA_SCALE");
    const char *frames_env = getenv("GRAMMA_TEST_FRAMES");
    const char *shot_env = getenv("GRAMMA_SCREENSHOT");
    SDL_RendererInfo info;

    memset(&g_pc, 0, sizeof(g_pc));
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMECONTROLLER) < 0) {
        return GR_ERR_BACKEND;
    }
    if (scale_env != NULL) {
        scale = atoi(scale_env);
    }
    if (scale < 1) {
        scale = 1;
    } else if (scale > 8) {
        scale = 8;
    }
    g_pc.scale = scale;
    g_pc.width = cfg->width;
    g_pc.height = cfg->height;
    g_pc.cfg = cfg;
    g_pc.test_frames = (frames_env != NULL) ? (uint32_t)atoi(frames_env) : 0;
    if (shot_env != NULL) {
        strncpy(g_pc.screenshot, shot_env, sizeof(g_pc.screenshot) - 1);
    }

    g_pc.window = SDL_CreateWindow(cfg->title != NULL ? cfg->title : "Gramma",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        g_pc.width * scale, g_pc.height * scale, SDL_WINDOW_SHOWN);
    if (g_pc.window == NULL) {
        pc_quit();
        return GR_ERR_BACKEND;
    }
    memset(&info, 0, sizeof(info));
    g_pc.renderer = SDL_CreateRenderer(g_pc.window, -1,
                                       SDL_RENDERER_ACCELERATED);
    if (g_pc.renderer == NULL) {
        g_pc.renderer = SDL_CreateRenderer(g_pc.window, -1,
                                           SDL_RENDERER_SOFTWARE);
    }
    if (g_pc.renderer == NULL) {
        pc_quit();
        return GR_ERR_BACKEND;
    }
    g_pc.texture = SDL_CreateTexture(g_pc.renderer, SDL_PIXELFORMAT_RGB565,
                                     SDL_TEXTUREACCESS_STREAMING,
                                     g_pc.width, g_pc.height);
    g_pc.fb = (uint16_t *)malloc((size_t)g_pc.width * (size_t)g_pc.height *
                                 sizeof(uint16_t));
    if (g_pc.texture == NULL || g_pc.fb == NULL) {
        pc_quit();
        return GR_ERR_NO_MEMORY;
    }

    if (!pc_audio_init(cfg)) {
        SDL_LogWarn(SDL_LOG_CATEGORY_APPLICATION,
                    "Audio device unavailable; running muted.");
    }
    g_pc.start_tick = SDL_GetTicks();
    g_pc.last_frame_tick = g_pc.start_tick;
    pc_clear(g_pc.fb, g_pc.width, g_pc.height, 0);
    return GR_OK;
}

static void pc_quit(void)
{
    int p;
    for (p = 0; p < GR_PLAYER_COUNT; ++p) {
        if (g_pc.controllers[p] != NULL) {
            SDL_GameControllerClose(g_pc.controllers[p]);
            g_pc.controllers[p] = NULL;
        }
    }
    pc_audio_quit();
    if (g_pc.texture != NULL) {
        SDL_DestroyTexture(g_pc.texture);
    }
    if (g_pc.renderer != NULL) {
        SDL_DestroyRenderer(g_pc.renderer);
    }
    if (g_pc.window != NULL) {
        SDL_DestroyWindow(g_pc.window);
    }
    free(g_pc.fb);
    memset(&g_pc, 0, sizeof(g_pc));
    SDL_Quit();
}

static bool controller_button(SDL_GameController *pad, gr_button button)
{
    SDL_GameControllerButton map[] = {
        SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
        SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
        SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B,
        SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_Y,
        SDL_CONTROLLER_BUTTON_LEFTSHOULDER, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,
        SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_BACK
    };
    if (pad == NULL) {
        return false;
    }
    if (button <= GR_BTN_SELECT &&
        SDL_GameControllerGetButton(pad, map[button])) {
        return true;
    }
    if (button == GR_BTN_LEFT &&
        SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_LEFTX) < -8000) {
        return true;
    }
    if (button == GR_BTN_RIGHT &&
        SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_LEFTX) > 8000) {
        return true;
    }
    if (button == GR_BTN_UP &&
        SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_LEFTY) < -8000) {
        return true;
    }
    if (button == GR_BTN_DOWN &&
        SDL_GameControllerGetAxis(pad, SDL_CONTROLLER_AXIS_LEFTY) > 8000) {
        return true;
    }
    return false;
}

static void pc_open_controller(int device_index)
{
    int p;
    SDL_GameController *pad;

    if (g_pc.cfg == NULL) {
        return;
    }
    for (p = 0; p < (int)g_pc.cfg->players && p < GR_PLAYER_COUNT; ++p) {
        if (g_pc.controllers[p] == NULL) {
            break;
        }
    }
    if (p >= (int)g_pc.cfg->players || p >= GR_PLAYER_COUNT) {
        return;
    }
    pad = SDL_GameControllerOpen(device_index);
    if (pad != NULL) {
        g_pc.controllers[p] = pad;
    }
}

static void pc_frame_begin(void)
{
    SDL_Event event;
    const Uint8 *keyboard;
    uint8_t p, b;

    while (SDL_PollEvent(&event)) {
        if (event.type == SDL_QUIT) {
            g_pc.quit = true;
        } else if (event.type == SDL_CONTROLLERDEVICEADDED) {
            pc_open_controller(event.cdevice.which);
        } else if (event.type == SDL_CONTROLLERDEVICEREMOVED) {
            for (p = 0; p < GR_PLAYER_COUNT; ++p) {
                if (g_pc.controllers[p] != NULL &&
                    SDL_GameControllerFromInstanceID(event.cdevice.which) ==
                    g_pc.controllers[p]) {
                    SDL_GameControllerClose(g_pc.controllers[p]);
                    g_pc.controllers[p] = NULL;
                }
            }
        }
    }

    keyboard = SDL_GetKeyboardState(NULL);
    for (p = 0; p < GR_PLAYER_COUNT; ++p) {
        for (b = 0; b < GR_BTN_COUNT; ++b) {
            g_pc.prev[p][b] = g_pc.down[p][b];
            g_pc.down[p][b] = (bool)keyboard[keys[p][b]] ||
                              controller_button(g_pc.controllers[p],
                                                (gr_button)b);
        }
    }
}

static void pc_frame_draw(const gr_bg *bg, gr_actor *const *actors,
                          uint8_t actor_count)
{
    uint8_t i;

    pc_clear(g_pc.fb, g_pc.width, g_pc.height, 0);
    pc_draw_bg(g_pc.fb, g_pc.width, g_pc.height, bg,
               g_pc.palettes, g_pc.palette_used);
    for (i = 0; i < actor_count; ++i) {
        pc_draw_sprite(g_pc.fb, g_pc.width, g_pc.height,
                       &actors[i]->sprite, g_pc.palettes, g_pc.palette_used);
    }
}

/* Debug aid: dump a PPM on frame 2 so headless CI can inspect rendering. */
static void pc_save_screenshot(void)
{
    FILE *file = fopen(g_pc.screenshot, "wb");
    int i;

    if (file == NULL) {
        return;
    }
    fprintf(file, "P6\n%d %d\n255\n", g_pc.width, g_pc.height);
    for (i = 0; i < g_pc.width * g_pc.height; ++i) {
        uint16_t pixel = g_pc.fb[i];
        uint8_t rgb[3];
        rgb[0] = (uint8_t)(((pixel >> 11) & 0x1f) * 255 / 31);
        rgb[1] = (uint8_t)(((pixel >> 5) & 0x3f) * 255 / 63);
        rgb[2] = (uint8_t)((pixel & 0x1f) * 255 / 31);
        fwrite(rgb, 1, 3, file);
    }
    fclose(file);
}

static void pc_frame_end(void)
{
    uint32_t now, elapsed;
    int delay;

    (void)gr_overlay_flush();
    SDL_UpdateTexture(g_pc.texture, NULL, g_pc.fb,
                      (int)(g_pc.width * sizeof(uint16_t)));
    SDL_RenderClear(g_pc.renderer);
    SDL_RenderCopy(g_pc.renderer, g_pc.texture, NULL, NULL);
    SDL_RenderPresent(g_pc.renderer);

    ++g_pc.frame_number;
    if (g_pc.screenshot[0] != '\0' && g_pc.frame_number == 2) {
        pc_save_screenshot();
    }
    if (g_pc.test_frames != 0 && g_pc.frame_number >= g_pc.test_frames) {
        g_pc.quit = true;
    }

    pc_audio_tick(16);
    now = SDL_GetTicks();
    elapsed = now - g_pc.last_frame_tick;
    delay = 16 - (int)elapsed;
    if (delay > 0) {
        SDL_Delay((uint32_t)delay);
    }
    g_pc.last_frame_tick = SDL_GetTicks();
}

static bool pc_pad_down(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return g_pc.down[player][button];
}

static bool pc_pad_pressed(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return g_pc.down[player][button] && !g_pc.prev[player][button];
}

static bool pc_pad_released(gr_player player, gr_button button)
{
    if (player >= GR_PLAYER_COUNT || button >= GR_BTN_COUNT) {
        return false;
    }
    return !g_pc.down[player][button] && g_pc.prev[player][button];
}

static void pc_palette_load(uint8_t slot, const gr_color *colors, uint8_t count)
{
    uint8_t i;
    if (slot >= GR_MAX_PALETTES) {
        return;
    }
    if (count > GR_PALETTE_COLORS) {
        count = GR_PALETTE_COLORS;
    }
    for (i = 0; i < count; ++i) {
        g_pc.palettes[slot][i] = colors[i];
    }
    g_pc.palette_used[slot] = true;
}

static uint32_t pc_ticks(void)
{
    return SDL_GetTicks() - g_pc.start_tick;
}

static bool pc_quit_requested(void)
{
    return g_pc.quit;
}

/* The software renderer reads generated tilesets directly, so staged overlay
 * bytes have nowhere to go. Accept and discard them to keep one portable API. */
static gr_result pc_overlay_tiles(uint8_t dest, const uint8_t *data,
                                  uint16_t count, bool sprite)
{
    (void)dest;
    (void)data;
    (void)count;
    (void)sprite;
    return GR_OK;
}

static gr_result pc_overlay_nametable(uint8_t x, uint8_t y, uint8_t w,
                                      uint8_t h, const uint8_t *tiles)
{
    (void)x;
    (void)y;
    (void)w;
    (void)h;
    (void)tiles;
    return GR_OK;
}

const gr_backend gr_backend_pc = {
    "pc",
    { 0xffffu, 0xffffu },
    pc_init,
    pc_quit,
    pc_frame_begin,
    pc_frame_draw,
    pc_frame_end,
    pc_pad_down,
    pc_pad_pressed,
    pc_pad_released,
    pc_palette_load,
    pc_backend_music_play,
    pc_backend_music_stop,
    pc_backend_sfx_play,
    pc_ticks,
    pc_quit_requested,
    pc_overlay_tiles,
    pc_overlay_nametable
};
