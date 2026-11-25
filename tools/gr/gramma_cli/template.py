"""`gr new`: writes a small, playable starter project."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from PIL import Image, ImageDraw

MESON_BUILD = """subdir('generated/' + target)

game = executable('game',
    [files('src/main.c'), generated_sources],
    dependencies: [gramma_dep, gramma_pc_dep],
)
"""

PROJECT_TOML = '''[project]
name = "{name}"
default_target = "pc"
max_sprites = 1
width = 256
height = 224

[[image]]
name = "hero"
file = "assets/hero.png"
kind = "sprite"
bpp = 4
frame_width = 16
frame_height = 16

[[image]]
name = "ground"
file = "assets/ground.png"
kind = "background"
bpp = 4

[[audio]]
name = "blip"
file = "assets/blip.wav"
sample_rate = 22050

[budgets.pc]
rom_kb = 512
vram_tiles = 1024

[target.gb.image.hero]
bpp = 2

[target.gb.image.ground]
bpp = 2

# nrom, mmc1 and mmc3 are supported. PRG stays at 32 KB; CHR banks are 8 KB
# and may be 1, 2, 4 ... for mappers that support switching.
[mapper.nes]
id = "nrom"
prg_banks = 2
chr_banks = 1
'''

MAIN_C = '''#include <gramma/gramma.h>
#include <string.h>

extern const gr_tileset hero_tileset;
extern const gr_tileset ground_tileset;
extern const gr_map ground_map;
extern const gr_sfx_def blip_sfx;

static gr_bg ground;

static void hero_update(gr_actor *actor, gr_fixed dt)
{
    gr_fixed speed = gr_itof(80);
    actor->vx = 0;
    actor->vy = 0;
    if (gr_pad_down(GR_PLAYER_1, GR_BTN_LEFT))  actor->vx = -speed;
    if (gr_pad_down(GR_PLAYER_1, GR_BTN_RIGHT)) actor->vx =  speed;
    if (gr_pad_down(GR_PLAYER_1, GR_BTN_UP))    actor->vy = -speed;
    if (gr_pad_down(GR_PLAYER_1, GR_BTN_DOWN))  actor->vy =  speed;
    if (gr_pad_pressed(GR_PLAYER_1, GR_BTN_A)) {
        gr_sfx_play(0, 1);
    }
    actor->x = gr_fclamp(actor->x, 0, gr_itof(GR_SCREEN_W - 16));
    actor->y = gr_fclamp(actor->y, 0, gr_itof(GR_SCREEN_H - 16));
    (void)dt;
}

static void start(void)
{
    gr_bg_init(&ground, &ground_tileset, &ground_map, 0);
    {
        gr_actor_def def;
        memset(&def, 0, sizeof(def));
        def.name = "hero";
        def.tileset = &hero_tileset;
        def.frame_w = 2;
        def.frame_h = 2;
        def.x = gr_itof(120);
        def.y = gr_itof(104);
        def.update = hero_update;
        gr_actor_spawn(&def);
    }
    {
        gr_scene scene;
        memset(&scene, 0, sizeof(scene));
        scene.name = "field";
        scene.bg = &ground;
        gr_scene_load(&scene);
    }
}

static const gr_sfx_def *const sfx_table[] = { &blip_sfx };

static const gr_config config = {
    "Gramma starter", GR_SCREEN_W, GR_SCREEN_H, 8, 1,
    { GR_BUTTON_BIT(GR_BTN_UP) | GR_BUTTON_BIT(GR_BTN_DOWN) |
      GR_BUTTON_BIT(GR_BTN_LEFT) | GR_BUTTON_BIT(GR_BTN_RIGHT) |
      GR_BUTTON_BIT(GR_BTN_A), 0 },
    start, NULL, NULL, sfx_table, 1
};

int main(void)
{
    if (gr_init(&config) != GR_OK) {
        return 1;
    }
    return gr_run();
}
'''


def create_project(directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "src").mkdir()
    (directory / "assets").mkdir()
    (directory / "project.toml").write_text(
        PROJECT_TOML.format(name=name), encoding="utf-8")
    (directory / "meson.build").write_text(MESON_BUILD, encoding="utf-8")
    (directory / "src" / "main.c").write_text(MAIN_C, encoding="utf-8")

    hero = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hero)
    draw.rectangle((2, 2, 13, 13), fill=(40, 120, 220, 255))
    draw.rectangle((4, 4, 11, 8), fill=(235, 235, 245, 255))
    hero.save(directory / "assets" / "hero.png")

    ground = Image.new("RGBA", (128, 128), (28, 96, 48, 255))
    draw = ImageDraw.Draw(ground)
    for y in range(0, 128, 16):
        for x in range(0, 128, 16):
            if ((x // 16) + (y // 16)) % 2 == 0:
                draw.rectangle((x, y, x + 7, y + 7), fill=(36, 112, 56, 255))
    ground.save(directory / "assets" / "ground.png")

    rate, seconds = 22050, 0.12
    with wave.open(str(directory / "assets" / "blip.wav"), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        frames = []
        for i in range(int(rate * seconds)):
            envelope = 1.0 - i / (rate * seconds)
            value = int(12000 * envelope *
                        math.sin(2 * math.pi * 660 * i / rate))
            frames.append(struct.pack("<h", value))
        output.writeframes(b"".join(frames))
