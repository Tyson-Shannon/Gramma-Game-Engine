"""``gr new``: writes small, playable starter projects.

Every template is self-contained: it owns its assets, source and documentation.
The default ``c`` template teaches the portable C API; the two Grain templates
show the ahead-of-time language and the optional tracker score.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from PIL import Image, ImageDraw

C_MESON_BUILD = """subdir('generated/' + target)

game = executable('game',
    [files('src/main.c'), generated_sources],
    dependencies: [gramma_dep, gramma_pc_dep],
)
"""

GRAIN_MESON_BUILD = """subdir('generated/' + target)

# Grain is transpiled into one of generated_sources by the asset pipeline; there
# is deliberately no main.c and no runtime interpreter.
game = executable('game',
    generated_sources,
    dependencies: [gramma_dep, gramma_pc_dep],
)
"""

C_PROJECT_TOML = '''[project]
name = "{name}"
schema_version = 1
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

GRAIN_PROJECT_TOML = '''[project]
name = "{name}"
schema_version = 1
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
{music_asset}
[budgets.pc]
rom_kb = 512
vram_tiles = 1024

[target.gb.image.hero]
bpp = 2

[target.gb.image.ground]
bpp = 2

[mapper.nes]
id = "nrom"
prg_banks = 2
chr_banks = 1

# Each .grain file is one C translation unit; the pipeline emits grain_game.c.
[grain]
sources = ["src/game.grain"]
'''

MUSIC_ASSET = '''[[music]]
name = "theme"
file = "assets/theme.tick"

'''

THEME_SCORE = '''; Starter theme - Gramma tracker score v1
; One row is a 16th-note tick. "-" sustains, "off" cuts, NOTE:VOL triggers.
bpm 120
fps 50
channels 2
wave square

pattern a
    C5:12 C3:11
    -     -
    E5:12 -
    -     -
    G5:12 C3:11
    -     -
    E5:12 -
    off   off

order a a a a
'''

C_MAIN = '''#include <gramma/gramma.h>
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

GRAIN_MAIN = '''# A complete game in Grain. No interpreter: gr build transpiles this file to
# generated/<target>/grain_game.c and compiles it with the same C API the C
# template uses. D-pad moves the hero; A plays the blip.

extern tileset hero_tileset
extern tileset ground_tileset
extern map ground_map
extern sfx blip_sfx
{music_extern}

entity Hero {
    tileset: tileset = hero_tileset;
    frame_w: int = 2;
    frame_h: int = 2;
    speed: fixed = 1.25;
    beeps: int = 0;

    on_update(dt: fixed) {
        vx = 0;
        vy = 0;
        if (pad_down(P1, LEFT)) {
            vx = -speed;
        }
        if (pad_down(P1, RIGHT)) {
            vx = speed;
        }
        if (pad_down(P1, UP)) {
            vy = -speed;
        }
        if (pad_down(P1, DOWN)) {
            vy = speed;
        }
        if (pad_pressed(P1, A)) {
            sfx_play(0, 1);
            beeps += 1;
        }
        x = fclamp(x + vx, 0, itof(SCREEN_W - 16));
        y = fclamp(y + vy, 0, itof(SCREEN_H - 16));
        show(self, 0, ftoi(x), ftoi(y));
    }
}

scene Field {
    tileset: tileset = ground_tileset;
    background: map = ground_map;
}

game {
    title = "Grain starter";
    width = 256;
    height = 224;
    max_actors = 4;
    players = 1;
    required_buttons = [UP, DOWN, LEFT, RIGHT, A];

    on_init() {
        load_scene(Field);
        spawn(Hero, itof(120), itof(104));
{music_play}    }
}
'''

MUSIC_EXTERN = 'extern song theme\n'
MUSIC_PLAY = '        music_play(theme);\n'

README = '''# {name}

Generated by `gr new --template {template}`.

## Play it in under a minute

```sh
cd {directory}
./tools/gr/gr run --target pc --project .
```

Use the D-pad to move and A to play the sound{music_note}. `gr run` builds the
PC simulator and launches it with SDL2. Set `SDL_VIDEODRIVER=dummy` for a
headless smoke run, or pass `--frames 10` to exit after ten frames.

## Build for a console

```sh
./tools/gr/gr build --target gb --project .
./tools/gr/gr build --target nes --project .
./tools/gr/gr build --target sms --project .
./tools/gr/gr build --target sms --gg --project .
```

Each target compiles the same source and generated assets. The CLI downloads
missing toolchains into `~/.cache/gramma`; `gr doctor` reports what is present.

## Files

- `project.toml`: assets, budgets and optional per-target overrides.
- `{source}`: the game source ({source_kind}).
- `assets/`: generated PNG/WAV{assets_note}, owned by this project.
- `meson.build`: tiny wrapper around the pipeline's generated source list.

Generated C lives in `generated/<target>/` and is rebuilt by every `gr build`.
Do not edit it.

## Next steps

- Read the [generated API reference](../../../docs/generated/api-reference.md)
  and the [hand-written API guide](../../../docs/api.md).
- Read [docs/asset-pipeline.md](../../../docs/asset-pipeline.md) to add art,
  music or a Tiled map.
- For Grain templates, see [docs/grain.md](../../../docs/grain.md). For the C
  template, the portable API lives in `core/include/gramma/gramma.h`.
'''

TEMPLATES = {
    "c": {
        "description": "portable C starter with art and a blip",
        "meson": C_MESON_BUILD,
        "project": C_PROJECT_TOML,
        "source_path": "src/main.c",
        "source_text": C_MAIN,
        "source_kind": "portable C89/C99",
        "music": False,
    },
    "grain": {
        "description": "playable Grain game compiled ahead of time to C",
        "meson": GRAIN_MESON_BUILD,
        "project": GRAIN_PROJECT_TOML,
        "source_path": "src/game.grain",
        "source_text": GRAIN_MAIN,
        "source_kind": "Grain (AOT)",
        "music": False,
    },
    "grain-music": {
        "description": "Grain game with a tracker score and SFX",
        "meson": GRAIN_MESON_BUILD,
        "project": GRAIN_PROJECT_TOML,
        "source_path": "src/game.grain",
        "source_text": GRAIN_MAIN,
        "source_kind": "Grain (AOT)",
        "music": True,
    },
}


def create_project(directory: Path, name: str, template: str = "c") -> None:
    """Create a playable starter project in *directory*."""
    if template not in TEMPLATES:
        choices = ", ".join(sorted(TEMPLATES))
        raise ValueError(f"unknown template '{template}' (choose {choices})")
    spec = TEMPLATES[template]
    music = bool(spec["music"])

    directory.mkdir(parents=True, exist_ok=False)
    (directory / "src").mkdir()
    (directory / "assets").mkdir()

    project = spec["project"].format(
        name=name, music_asset=MUSIC_ASSET if music else "")
    (directory / "project.toml").write_text(project, encoding="utf-8")
    (directory / "meson.build").write_text(spec["meson"], encoding="utf-8")
    source = (spec["source_text"]
              .replace("{music_extern}", MUSIC_EXTERN if music else "")
              .replace("{music_play}", MUSIC_PLAY if music else ""))
    source_path = directory / spec["source_path"]
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source, encoding="utf-8")

    (directory / "README.md").write_text(
        README.format(
            name=name,
            template=template,
            directory=directory,
            source=spec["source_path"],
            source_kind=spec["source_kind"],
            music_note=" and A starts a two-channel theme" if music else "",
            assets_note=" and a tracker score" if music else ""),
        encoding="utf-8")

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

    if music:
        (directory / "assets" / "theme.tick").write_text(
            THEME_SCORE, encoding="utf-8")
