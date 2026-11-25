# Gramma API v0 (draft)

Public header: [`core/include/gramma/gramma.h`](../core/include/gramma/gramma.h).
It compiles as C99 on the host, with GBDK-2020's SDCC on the Game Boy, cc65 on
the NES and SDCC + devkitSMS on SMS/Game Gear. For a declaration-by-declaration
index of every public header, see the
[generated API reference](generated/api-reference.md); `gr docs` regenerates it
and `gr docs --check` verifies it in CI. This file remains the hand-written
narrative guide.

## Grain (ahead-of-time language)

Grain is not a second runtime: it transpiles to the exact functions below. A
`.grain` source emits one C translation unit containing entity pools, scene
state, handlers, a `gr_config` and `main()`. For example, `show(self, ...)` in
an entity handler emits `gr_sprite_show(&self->actor->sprite, ...)`, `spawn()`
emits `gr_actor_spawn(&def)`, fixed-point operators emit `gr_fmul`/`gr_fdiv`,
and the generated `game_init`/`game_update`/`game_draw` functions become the
`gr_config` callbacks. The output is C89-clean so every backend consumes it.
Grain v1 adds typed locals, typed user functions (emitted as static
`grain_fn_<name>()` C functions) and fixed arrays (`T[N]`, `[...]`, `a[i]`);
declarations are hoisted to function starts so cc65/SDCC accept the output.

Use `gr grain --check` for diagnostics (`file:line:col: error: message`) and
`gr build` to compile the generated C. The optional
[`editors/vscode-grain/`](../editors/vscode-grain/) extension now starts `gr
lsp`, a dependency-free stdio JSON-RPC language server with diagnostics,
completion, go-to-definition, hover, document symbols and single-file rename. It
falls back to `gr grain --check` when the server cannot start.
`examples/grain-demo/` is a complete game written only in Grain. Full syntax,
builtins and limits are in [`grain.md`](grain.md).

## Lifecycle

```c
gr_result gr_init(const gr_config *cfg);
void      gr_quit(void);
int       gr_run(void);
void      gr_begin_frame(void);
void      gr_end_frame(void);
bool      gr_quit_requested(void);
void      gr_request_quit(void);
uint32_t  gr_ticks(void);
```

`gr_config` declares the logical screen size (`GR_SCREEN_W`/`GR_SCREEN_H` are
per-target defaults), maximum actors, player count, required input buttons and
optional `game_init`/`game_update`/`game_draw` callbacks. `gr_run` calls
`game_init` once, then runs a 60 Hz fixed-step loop: scene update, game update,
actor integration, scene draw, game draw, backend draw, vsync-equivalent wait.

Required buttons are checked at `gr_init`. If a target cannot provide one,
initialisation fails with `GR_ERR_UNSUPPORTED` instead of silently ignoring it.

## Actors and scenes

```c
gr_result gr_scene_load(gr_scene *scene);
gr_scene *gr_scene_current(void);
void      gr_actor_clear(void);
gr_actor *gr_actor_spawn(const gr_actor_def *def);
void      gr_actor_destroy(gr_actor *actor);
uint8_t   gr_actor_count(void);
void      gr_actor_update_all(gr_fixed dt);
```

Actors come from a static pool (`GR_MAX_ACTORS`, see
[`target.h`](../core/include/gramma/target.h)). An actor owns a `gr_sprite`
with position, frame and flip state. Its optional `update` callback is called
before velocity integration.

## Sprites, backgrounds, palettes

```c
void gr_bg_init(gr_bg *bg, const gr_tileset *tileset, const gr_map *map,
                uint8_t pal_slot);
void gr_bg_set_scroll(gr_bg *bg, int16_t x, int16_t y);
void gr_sprite_show(gr_sprite *s, uint8_t pal_slot, int16_t x, int16_t y);
void gr_sprite_hide(gr_sprite *s);
void gr_sprite_set_frame(gr_sprite *s, uint8_t frame);
void gr_sprite_set_flip(gr_sprite *s, bool x, bool y);
gr_result gr_palette_load(uint8_t slot, const gr_color *colors, uint8_t count);
```

`gr_tileset` contains 8x8 packed tiles plus its source palette. Index 0 is
transparent for sprites. A loaded palette slot overrides a tileset's own
palette; otherwise the generated palette is used. `gr_map` is a row-major
array of tile indices; backgrounds wrap at map edges when scrolled. `gr_bg_set_scroll`
accepts pixel coordinates; the NES applies coarse scrolling by rewriting a
nametable column and fine scrolling through the custom NMI, so sub-tile shifts
work. On NES, RGB555 colors are quantized to the nearest 2C02 palette entry;
each nametable currently uses one uniform background palette slot. On SMS/GG,
colors convert to CRAM bytes/words with 16 entries per BG and sprite palette;
background tiles occupy VRAM 0-255 and sprite tiles 256-511.

## Input

```c
bool gr_pad_down(gr_player player, gr_button button);
bool gr_pad_pressed(gr_player player, gr_button button);
bool gr_pad_released(gr_player player, gr_button button);
```

Canonical buttons: UP, DOWN, LEFT, RIGHT, A, B, X, Y, L, R, START, SELECT.
`GR_PAD_PLAYERS` tells games how many controllers the target can address. The
NES backend addresses two eight-button pads (D-pad, A, B, START, SELECT);
X/Y/L/R are unavailable. The Game Boy backend addresses one four-button pad.
SMS/GG address two D-pads with two buttons: A/B map to buttons 1/2, START aliases
button 1 on Master System and uses the real START bit on Game Gear. X/Y/L/R are
unavailable.

## Audio

```c
gr_result gr_music_play(const gr_song *song);
void      gr_music_stop(void);
void      gr_sfx_play(uint16_t sfx_id, uint8_t channel);
```

Music is a compiled 16th-note event stream, not a decoded audio file, so each
target can recompile it for its sound chip. `gr_song` carries a trailing
`const uint8_t *psg` member: generated songs set it to an uncompressed
PSGlib-format stream on SMS/GG and to `NULL` elsewhere, so the same symbol
works on every target. Hand-written four-field `gr_song` initializers remain
valid C and leave `psg` as `NULL`. `[[music]]` scores compile to that symbol;
see [`asset-pipeline.md`](asset-pipeline.md#music-tracker-scores).

`gr_sfx_def` describes either a synthesized wave (square/triangle/saw/noise) or
pipeline-converted PCM. The Game Boy backend approximates PCM SFX with a
tone/noise channel; the NES backend also substitutes a short pulse tone because
DMC playback is not yet implemented. SMS/GG play ordinary note streams as
SN76489 tones on channel 0, while generated songs with `psg != NULL` use a small
built-in PSGlib-format interpreter for up to four channels (three tone and one
noise). Compressed PSG data is not supported: the player stops on any reserved
or compression marker. Music and SFX share the PSG, so an SFX can temporarily
override a music channel.

## Bank switching (opt-in)

Concrete mappers are not part of the base API. Games that need them include
[`gramma/bank.h`](../core/include/gramma/bank.h) and the matching target header:
[`gramma/target/nes/mapper.h`](../core/include/gramma/target/nes/mapper.h),
[`gramma/target/gb/mapper.h`](../core/include/gramma/target/gb/mapper.h) or
[`gramma/target/sms/mapper.h`](../core/include/gramma/target/sms/mapper.h).
None of these headers is pulled in by `gramma.h`.

```c
gr_result gr_bank_set_init(gr_bank_set *set, uint8_t slot_count,
                           gr_bank_write_fn write, void *user);
gr_result gr_bank_select(gr_bank_set *set, uint8_t slot, uint16_t bank);
uint8_t   gr_bank_slots(const gr_bank_set *set);
uint16_t  gr_bank_current(const gr_bank_set *set, uint8_t slot);

typedef struct {
    gr_bank_set *set;
    uint8_t      slot;
    uint16_t     bank_a, bank_b;
    bool         alternate;
} gr_bank_switch;

gr_result gr_bank_switch_init(gr_bank_switch *sw, gr_bank_set *set,
                              uint8_t slot, uint16_t bank_a, uint16_t bank_b);
uint16_t  gr_bank_switch_toggle(gr_bank_switch *sw);
gr_result gr_bank_switch_reset(gr_bank_switch *sw);
```

A bank set caches the selected bank for each logical slot and calls a backend
writer when one is installed. Zero slots means fixed ROM, so `gr_bank_select`
returns `GR_ERR_INVALID_ARG`. `gr_bank_switch` is a small game-side helper for
the common case of two versions of the same tile indices; `test-kart` uses it to
toggle between its two CHR banks with B.

The NES extension adds `gr_nes_mapper_init_hw()` for tests and standalone use,
`gr_nes_mapper_register_write()` for raw mapper writes, and runtime accessors
installed by `gr_init()`:

```c
gr_nes_mapper gr_nes_mapper_runtime_id(void);
gr_bank_set *gr_nes_mapper_prg_banks(void);
gr_bank_set *gr_nes_mapper_chr_banks(void);
```

MMC1 exposes one 16 KB PRG slot and two 4 KB CHR slots via its 5-bit serial
protocol (control `$1E` enables 4 KB CHR mode); MMC3 exposes two 8 KB PRG slots
(R6/R7) and four CHR slots (R0-R3 in 4 KB mode). The build driver emits NROM,
MMC1 or MMC3 headers from `[mapper.nes]` and the custom crt0 programs the mapper
at startup; the backend installs the same state with a real hardware writer so
games can switch banks during play. Prefer CHR switching: MMC3 PRG windows hold
the executing code. `gr_nes_prg_read()` reads data-only PRG banks from a
RAM-resident routine when a larger layout is configured. See
[`docs/banking.md`](banking.md).

`[mapper.nes]` supports 2, 4, 8 ... 16 PRG banks of 16 KB on MMC1/MMC3 (NROM
stays at two) and 1, 2, 4 ... 16 CHR banks of 8 KB. `gr check`, `gr build` and
`gr run` accept `--mapper`, `--prg-banks` and `--chr-banks` overrides. Images may
set `chr_bank` and `chr_tile` in
`[[image]]` or a `[target.nes.image.<name>]` override. Tile indices are local
to a 4 KB pattern table inside the selected 8 KB bank, and the pipeline rejects
overlaps or out-of-range placements. Mapper registers select 4 KB halves, so
convert an asset bank with `GR_NES_CHR_BANK4()`:

```c
/* Select the first 4 KB half of 8 KB CHR bank 1 for MMC3 sprite slot 2. */
(void)gr_bank_select(gr_nes_mapper_chr_banks(), 2u,
                     GR_NES_CHR_BANK4(1));
```

### Game Boy MBC extension

A plain 32 KB Game Boy cartridge has no switchable windows. MBC1/MBC3/MBC5 add
one 16 KB ROM window at `$4000-$7FFF` and, when SRAM is present, one 8 KB RAM
window at `$A000-$BFFF`. Bank 0 stays fixed, so the logical ROM banks are
1..`rom_banks-1`.

```c
#include <gramma/target/gb/mapper.h>

gr_result gr_gb_mapper_init(gr_gb_mapper_state *state, gr_gb_mapper id,
                            uint8_t rom_banks, uint8_t ram_banks,
                            gr_gb_bank_write_fn write, void *user);
gr_gb_mapper gr_gb_mapper_runtime_id(void);
uint8_t   gr_gb_mapper_rom_bank_count(void);
uint8_t   gr_gb_mapper_ram_bank_count(void);
gr_bank_set *gr_gb_mapper_rom_banks(void);
gr_bank_set *gr_gb_mapper_ram_banks(void);
```

`gr_gb_mapper_init()` accepts an injected writer for tests;
`gr_init()` installs the runtime state from the build-time `[mapper.gb]`
configuration with real `SWITCH_ROM`/`SWITCH_RAM` writes. The shipped example
calls a `BANKED` helper in bank 2 that returns `0x5a`; GBDK's fixed-code
trampoline restores the previous window on return. The generic
`gr_bank_select()` is exercised by unit tests but is not used to restore banks
around that helper, because the trampoline already does it safely.

`[mapper.gb]` accepts `id = "none" | "mbc1" | "mbc3" | "mbc5"`,
`rom_banks` (16 KB banks, including bank 0) and `ram_banks` (8 KB banks).
`gr check`, `gr build` and `gr run` accept `--gb-mapper`, `--gb-rom-banks` and
`--gb-ram-banks` overrides. MBC1 caps ROM at 32 banks and SRAM at four banks;
MBC3/MBC5 allow 128 ROM banks, with SRAM capped at 4 and 16 banks respectively.

### SMS / Game Gear mapper extension

A two-bank SMS ROM is fixed: banks 0 and 1 occupy `$0000-$7FFF`. Larger Sega
mapper ROMs add one 16 KB slot at `$8000-$BFFF`, selected by writing bank
2..N-1 to `$FFFF`. Logical bank numbers match devkitSMS physical banks.

```c
#include <gramma/target/sms/mapper.h>

gr_result gr_sms_mapper_init(gr_sms_mapper_state *state, uint8_t rom_banks,
                             gr_sms_bank_write_fn write, void *user);
gr_result gr_sms_mapper_runtime_init(uint8_t rom_banks,
                                     gr_sms_bank_write_fn write, void *user);
uint8_t   gr_sms_mapper_rom_bank_count(void);
gr_bank_set *gr_sms_mapper_rom_banks(void);
```

`gr_init()` installs the runtime state with SMSlib's `SMS_mapROMBank()`.
`[mapper.sms] rom_banks` accepts 2, 4, 8 ... 64; `gr check/build/run` accept
`--sms-rom-banks`. The build writes the SEGA header size code, emits `BANKN`
segments for `bankN_*.c` files and checks bank sentinels in CI.

## Opt-in target system headers

Three more opt-in headers describe fixed console capabilities without adding
anything to `gramma.h`:

```c
#include <gramma/target/gb/system.h>   /* gr_gb_system_caps */
#include <gramma/target/nes/system.h>  /* gr_nes_system_caps */
#include <gramma/target/sms/system.h>  /* gr_sms_system_caps */
```

Each exports constants (tile byte count, bits per pixel, palette size/slots,
player count, screen size, plus NES nametable size or SMS sprite tile base) and
one query:

```c
gr_result gr_gb_system_query(gr_gb_system_caps *out);
gr_result gr_nes_system_query(gr_nes_system_caps *out);
gr_result gr_sms_system_query(gr_sms_system_caps *out);
```

A query fills `*out` only when the build defines the matching
`GRAMMA_TARGET_GB`, `GRAMMA_TARGET_NES` or `GRAMMA_TARGET_SMS`; otherwise it
returns `GR_ERR_UNSUPPORTED`. A null pointer returns `GR_ERR_INVALID_ARG`. This
lets portable code include all three headers, probe capabilities and fail
explicitly instead of inventing a runtime target detection layer. The generated
[API reference](generated/api-reference.md) indexes these headers alongside the
mapper and overlay extensions.

## Vblank overlays (opt-in)

Public header: [`gramma/overlay.h`](../core/include/gramma/overlay.h).

```c
#include <gramma/overlay.h>

#define GR_OVERLAY_MAX_OPS     8u
#define GR_OVERLAY_TILE_BYTES  256u   /* 16 GB tiles or 8 SMS tiles */
#define GR_OVERLAY_MAP_BYTES   64u    /* one 8x8 nametable patch */

gr_result gr_overlay_tiles(uint8_t dest, const uint8_t *src, uint16_t bytes,
                           bool sprite);
gr_result gr_overlay_nametable(uint8_t x, uint8_t y, uint8_t w, uint8_t h,
                               const uint8_t *tiles);
gr_result gr_overlay_flush(void);
void      gr_overlay_clear(void);
uint8_t   gr_overlay_pending(void);
```

Staging copies source bytes into a small work-RAM queue immediately, so an MBC
or mapper bank can be restored before vblank. Backends flush the queue from
their frame-end handler; games normally do not call `gr_overlay_flush()`.
On Game Boy and SMS both operations upload to VRAM after the vblank wait; SMS
tiles are 32 bytes each and sprite tiles must be at VRAM tile 256+. On NES CHR
is ROM, so `gr_overlay_tiles()` returns `GR_ERR_UNSUPPORTED`; switch the CHR bank
instead, and keep nametable patches within 64 PPU writes per vblank or
`gr_overlay_nametable()` returns `GR_ERR_NO_MEMORY`. The example uses the same
B press for GB/SMS tile/map overlays and an NES CHR bank toggle.

## Fixed-point math

`gr_fixed` is `int32.16` on 32-bit targets and `int16.6` on 8-bit targets.
Helpers: `gr_itof`, `gr_ftoi`, `gr_fmul`, `gr_fdiv`, `gr_fclamp`. No floats and
no libm dependency in the portable core.
