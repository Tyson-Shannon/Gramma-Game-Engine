# Generated API reference

This file is generated from the public headers by `gr docs`. Edit the headers, then regenerate; the narrative guide lives in [`api.md`](../api.md). `gramma.h` does not include any opt-in header listed below.

## Contents

- [Bank switching (bank.h)](#gramma-bank)
- [Base API (gramma.h)](#gramma-gramma)
- [Vblank overlays (overlay.h)](#gramma-overlay)
- [Game Boy mapper (target/gb/mapper.h)](#gramma-target-gb-mapper)
- [system](#gramma-target-gb-system)
- [NES mapper (target/nes/mapper.h)](#gramma-target-nes-mapper)
- [system](#gramma-target-nes-system)
- [SMS/GG mapper (target/sms/mapper.h)](#gramma-target-sms-mapper)
- [system](#gramma-target-sms-system)
- [Target limits and fixed-point helpers (target.h)](#gramma-target)
- [Public types (types.h)](#gramma-types)

## Bank switching (bank.h) {#gramma-bank}

Header: [`gramma/bank.h`](../../core/include/gramma/bank.h).

### Functions

#### `gr_bank_set_init`

  Initialise a logical bank set. slot_count must be <= GR_BANK_MAX_SLOTS.
```c
gr_result gr_bank_set_init(gr_bank_set *set, uint8_t slot_count, gr_bank_write_fn write, void *user);
```

#### `gr_bank_select`

  Select a bank in one slot; calls the backend writer when one is installed.
```c
gr_result gr_bank_select(gr_bank_set *set, uint8_t slot, uint16_t bank);
```

#### `gr_bank_slots`

  Query helpers. Invalid slots read as bank 0.
```c
uint8_t gr_bank_slots(const gr_bank_set *set);
```

#### `gr_bank_current`

```c
uint16_t gr_bank_current(const gr_bank_set *set, uint8_t slot);
```

#### `gr_bank_switch_init`

```c
gr_result gr_bank_switch_init(gr_bank_switch *sw, gr_bank_set *set, uint8_t slot, uint16_t bank_a, uint16_t bank_b);
```

#### `gr_bank_switch_toggle`

  Select the other bank and return the new value, or 0 on error.
```c
uint16_t gr_bank_switch_toggle(gr_bank_switch *sw);
```

#### `gr_bank_switch_reset`

  Select the first bank. Useful when loading a scene.
```c
gr_result gr_bank_switch_reset(gr_bank_switch *sw);
```

### Types

#### `gr_bank_set`

```c
typedef struct { uint8_t slot_count; uint16_t current[GR_BANK_MAX_SLOTS]; gr_bank_write_fn write; /* NULL for software-only bank sets */ void *user; } gr_bank_set;
```

#### `gr_bank_switch`

  Games often keep two versions of the same tile indices in different banks and flip between them during play. gr_bank_switch caches that pair so game code does not need to remember which raw bank is currently selected. The bank values are target-specific. On NES they are mapper register values, so use GR_NES_CHR_BANK4(n) for 8 KB asset banks.
```c
typedef struct { gr_bank_set *set; uint8_t slot; uint16_t bank_a; uint16_t bank_b; bool alternate; } gr_bank_switch;
```

### Constants and macros

#### `GR_BANK_MAX_SLOTS`

  Opt-in bank abstraction. This header is intentionally NOT included by gramma.h: most games never switch banks, and the portable base API stays a lowest-common-denominator contract. Target-specific headers (for example gramma/target/nes/mapper.h) describe which bank sets a mapper exposes.
```c
#define GR_BANK_MAX_SLOTS 8u
```

## Base API (gramma.h) {#gramma-gramma}

Header: [`gramma/gramma.h`](../../core/include/gramma/gramma.h).

### Functions

#### `gr_init`

```c
gr_result gr_init(const gr_config *cfg);
```

#### `gr_quit`

```c
void gr_quit(void);
```

#### `gr_run`

  Runs game_init, then a 60 Hz fixed-step loop until quit is requested.
```c
int gr_run(void);
```

#### `gr_begin_frame`

```c
void gr_begin_frame(void);
```

#### `gr_end_frame`

```c
void gr_end_frame(void);
```

#### `gr_quit_requested`

```c
bool gr_quit_requested(void);
```

#### `gr_request_quit`

```c
void gr_request_quit(void);
```

#### `gr_ticks`

```c
uint32_t gr_ticks(void);
```

#### `gr_scene_load`

```c
gr_result gr_scene_load(gr_scene *scene);
```

#### `gr_scene_current`

```c
gr_scene *gr_scene_current(void);
```

#### `gr_actor_clear`

```c
void gr_actor_clear(void);
```

#### `gr_actor_spawn`

```c
gr_actor *gr_actor_spawn(const gr_actor_def *def);
```

#### `gr_actor_destroy`

```c
void gr_actor_destroy(gr_actor *actor);
```

#### `gr_actor_count`

```c
uint8_t gr_actor_count(void);
```

#### `gr_actor_update_all`

```c
void gr_actor_update_all(gr_fixed dt);
```

#### `gr_palette_load`

```c
gr_result gr_palette_load(uint8_t slot, const gr_color *colors, uint8_t count);
```

#### `gr_bg_init`

```c
void gr_bg_init(gr_bg *bg, const gr_tileset *tileset, const gr_map *map, uint8_t pal_slot);
```

#### `gr_bg_set_scroll`

```c
void gr_bg_set_scroll(gr_bg *bg, int16_t x, int16_t y);
```

#### `gr_bg_set_nametable`

  Select one of four PPU nametables (NES; ignored elsewhere).
```c
void gr_bg_set_nametable(gr_bg *bg, uint8_t nametable);
```

#### `gr_bg_set_palette_map`

  Per-tile background palette indices (0..3), or NULL for one flat palette. The array must have at least map->width * map->height bytes and stay valid while the background is drawn.
```c
void gr_bg_set_palette_map(gr_bg *bg, const uint8_t *palette_map);
```

#### `gr_bg_attribute`

  Pack the four 16x16 regions inside one attribute block (ax, ay) into the 2-bits-per-region byte used by tile hardware. Portable so it can be tested on the host and shared by backends.
```c
uint8_t gr_bg_attribute(const gr_bg *bg, uint8_t ax, uint8_t ay);
```

#### `gr_sprite_show`

```c
void gr_sprite_show(gr_sprite *s, uint8_t pal_slot, int16_t x, int16_t y);
```

#### `gr_sprite_hide`

```c
void gr_sprite_hide(gr_sprite *s);
```

#### `gr_sprite_set_frame`

```c
void gr_sprite_set_frame(gr_sprite *s, uint8_t frame);
```

#### `gr_sprite_set_flip`

```c
void gr_sprite_set_flip(gr_sprite *s, bool x, bool y);
```

#### `gr_pad_down`

```c
bool gr_pad_down(gr_player player, gr_button button);
```

#### `gr_pad_pressed`

```c
bool gr_pad_pressed(gr_player player, gr_button button);
```

#### `gr_pad_released`

```c
bool gr_pad_released(gr_player player, gr_button button);
```

#### `gr_music_play`

```c
gr_result gr_music_play(const gr_song *song);
```

#### `gr_music_stop`

```c
void gr_music_stop(void);
```

#### `gr_sfx_play`

```c
void gr_sfx_play(uint16_t sfx_id, uint8_t channel);
```

## Vblank overlays (overlay.h) {#gramma-overlay}

Header: [`gramma/overlay.h`](../../core/include/gramma/overlay.h).

### Functions

#### `gr_overlay_tiles`

  Stage `bytes` of tile data into VRAM tile `dest`. The byte format is the native tile format of the target: GB/NES use 16 bytes per tile, SMS uses 32.
```c
gr_result gr_overlay_tiles(uint8_t dest, const uint8_t *src, uint16_t bytes, bool sprite);
```

#### `gr_overlay_nametable`

  Stage a rectangular patch of 8x8 tile indices at (x, y). Coordinates are in tiles and use the target's nametable origin.
```c
gr_result gr_overlay_nametable(uint8_t x, uint8_t y, uint8_t w, uint8_t h, const uint8_t *tiles);
```

#### `gr_overlay_flush`

  Apply and clear queued operations. Backends call this from their vblank handler; games normally do not need to call it.
```c
gr_result gr_overlay_flush(void);
```

#### `gr_overlay_clear`

```c
void gr_overlay_clear(void);
```

#### `gr_overlay_pending`

```c
uint8_t gr_overlay_pending(void);
```

### Constants and macros

#### `GR_OVERLAY_MAX_OPS`

  Bounds keep the queue small enough for 8-bit work RAM.
```c
#define GR_OVERLAY_MAX_OPS       8u
```

#### `GR_OVERLAY_TILE_BYTES`

```c
#define GR_OVERLAY_TILE_BYTES    256u   /* 16 tiles at 16 bytes each */
```

#### `GR_OVERLAY_MAP_BYTES`

```c
#define GR_OVERLAY_MAP_BYTES     64u    /* one 8x8 nametable patch */
```

## Game Boy mapper (target/gb/mapper.h) {#gramma-target-gb-mapper}

Header: [`gramma/target/gb/mapper.h`](../../core/include/gramma/target/gb/mapper.h).

### Functions

#### `gr_gb_mapper_init`

  Initialise an MBC state with an injected writer. Bank 0 is fixed, so the ROM set contains physical banks 1..rom_banks-1. The RAM set contains 0..ram_banks-1 and has zero slots when the cartridge has no SRAM.
```c
gr_result gr_gb_mapper_init(gr_gb_mapper_state *state, gr_gb_mapper id, uint8_t rom_banks, uint8_t ram_banks, gr_gb_bank_write_fn write, void *user);
```

#### `gr_gb_mapper_runtime_init`

  Runtime mapper owned by the Game Boy backend. `gr_init()` initialises it from the build-time [mapper.gb] configuration.
```c
gr_result gr_gb_mapper_runtime_init(gr_gb_mapper id, uint8_t rom_banks, uint8_t ram_banks, gr_gb_bank_write_fn write, void *user);
```

#### `gr_gb_mapper_runtime_id`

```c
gr_gb_mapper gr_gb_mapper_runtime_id(void);
```

#### `gr_gb_mapper_rom_bank_count`

```c
uint8_t gr_gb_mapper_rom_bank_count(void);
```

#### `gr_gb_mapper_ram_bank_count`

```c
uint8_t gr_gb_mapper_ram_bank_count(void);
```

#### `gr_gb_mapper_rom_banks`

```c
gr_bank_set *gr_gb_mapper_rom_banks(void);
```

#### `gr_gb_mapper_ram_banks`

```c
gr_bank_set *gr_gb_mapper_ram_banks(void);
```

### Types

#### `gr_gb_mapper_state`

```c
typedef struct { gr_gb_mapper id; uint8_t rom_banks; /* 16 KB banks, including fixed bank 0 */ uint8_t ram_banks; /* 8 KB banks, 0 when no SRAM */ gr_bank_set rom; gr_bank_set ram; gr_gb_bank_write_fn write; void *user; } gr_gb_mapper_state;
```

### Constants and macros

#### `GR_GB_MAPPER_NONE`

  Opt-in Game Boy MBC extension. A plain 32 KB ROM has no switchable banks; MBC1/MBC3/MBC5 expose one 16 KB ROM window at $4000-$7FFF and, when the cartridge has SRAM, one 8 KB RAM window at $A000-$BFFF. See docs/banking.md.
```c
GR_GB_MAPPER_NONE
```

#### `GR_GB_MAPPER_MBC1`

  Opt-in Game Boy MBC extension. A plain 32 KB ROM has no switchable banks; MBC1/MBC3/MBC5 expose one 16 KB ROM window at $4000-$7FFF and, when the cartridge has SRAM, one 8 KB RAM window at $A000-$BFFF. See docs/banking.md.
```c
GR_GB_MAPPER_MBC1
```

#### `GR_GB_MAPPER_MBC3`

  Opt-in Game Boy MBC extension. A plain 32 KB ROM has no switchable banks; MBC1/MBC3/MBC5 expose one 16 KB ROM window at $4000-$7FFF and, when the cartridge has SRAM, one 8 KB RAM window at $A000-$BFFF. See docs/banking.md.
```c
GR_GB_MAPPER_MBC3
```

#### `GR_GB_MAPPER_MBC5`

  Opt-in Game Boy MBC extension. A plain 32 KB ROM has no switchable banks; MBC1/MBC3/MBC5 expose one 16 KB ROM window at $4000-$7FFF and, when the cartridge has SRAM, one 8 KB RAM window at $A000-$BFFF. See docs/banking.md.
```c
GR_GB_MAPPER_MBC5
```

#### `GR_GB_BANK_ROM`

```c
#define GR_GB_BANK_ROM 0u
```

#### `GR_GB_BANK_RAM`

```c
#define GR_GB_BANK_RAM 1u
```

#### `GR_GB_MAPPER`

  Build-time defaults; the build driver overrides these with -D flags.
```c
#define GR_GB_MAPPER 0
```

#### `GR_GB_ROM_BANKS`

```c
#define GR_GB_ROM_BANKS 2u
```

#### `GR_GB_RAM_BANKS`

```c
#define GR_GB_RAM_BANKS 0u
```

## system {#gramma-target-gb-system}

Header: [`gramma/target/gb/system.h`](../../core/include/gramma/target/gb/system.h).

### Functions

#### `gr_gb_system_query`

  Fill *out with GB capabilities. Returns GR_ERR_UNSUPPORTED on other targets.
```c
gr_result gr_gb_system_query(gr_gb_system_caps *out);
```

### Types

#### `gr_gb_system_caps`

```c
typedef struct { uint8_t tile_bytes; /* 16 for a native 2bpp CHR tile */ uint8_t bpp; uint8_t palette_colors; uint8_t palette_slots; uint8_t players; uint16_t screen_w; uint16_t screen_h; const char *name; } gr_gb_system_caps;
```

### Constants and macros

#### `GR_GB_TILE_BYTES`

  Opt-in Game Boy system information. Include this header only in GB builds or in portable code prepared to handle GR_ERR_UNSUPPORTED. It is not part of gramma.h and does not add a runtime dependency to the base API.
```c
#define GR_GB_TILE_BYTES      16u
```

#### `GR_GB_TILE_BPP`

```c
#define GR_GB_TILE_BPP        2u
```

#### `GR_GB_PALETTE_COLORS`

```c
#define GR_GB_PALETTE_COLORS  4u
```

#### `GR_GB_PALETTE_SLOTS`

```c
#define GR_GB_PALETTE_SLOTS   8u
```

#### `GR_GB_PLAYERS`

```c
#define GR_GB_PLAYERS         1u
```

#### `GR_GB_SCREEN_W`

```c
#define GR_GB_SCREEN_W        160u
```

#### `GR_GB_SCREEN_H`

```c
#define GR_GB_SCREEN_H        144u
```

## NES mapper (target/nes/mapper.h) {#gramma-target-nes-mapper}

Header: [`gramma/target/nes/mapper.h`](../../core/include/gramma/target/nes/mapper.h).

### Functions

#### `gr_nes_mapper_init`

  Initialise a mapper with no hardware writer. Only NROM is supported here; MMC1/MMC3 IDs return GR_ERR_UNSUPPORTED so callers cannot silently create a banked mapper without a register writer.
```c
gr_result gr_nes_mapper_init(gr_nes_mapper_state *state, gr_nes_mapper id);
```

#### `gr_nes_mapper_init_hw`

  Initialise a mapper with hardware register access. MMC1 installs one 16 KB PRG slot and two 4 KB CHR slots; MMC3 installs two 8 KB PRG slots and four 2 KB CHR slots. Both program their default control register and bank 0.
```c
gr_result gr_nes_mapper_init_hw(gr_nes_mapper_state *state, gr_nes_mapper id, gr_nes_io_write_fn io_write, void *io_user);
```

#### `gr_nes_mapper_register_write`

  Apply one raw register write. MMC1 accumulates five serial bits before updating a register; MMC3 latches $8000/$8001 writes. Exposed so backends and tests can drive the same code path used by the bank writers.
```c
void gr_nes_mapper_register_write(gr_nes_mapper_state *state, uint16_t address, uint8_t value);
```

#### `gr_nes_mapper_runtime_init`

  Runtime mapper owned by the NES backend. `gr_init()` initialises it from the build-time `[mapper.nes]` configuration with a real hardware writer; games should not call the init function themselves.
```c
gr_result gr_nes_mapper_runtime_init(gr_nes_mapper id, gr_nes_io_write_fn io_write, void *io_user);
```

#### `gr_nes_mapper_init_hw_layout`

  Hardware init with an explicit 16 KB PRG bank count. Larger layouts keep code in the final two banks and expose earlier banks as data; MMC1/MMC3 startup registers must select those final banks.
```c
gr_result gr_nes_mapper_init_hw_layout(gr_nes_mapper_state *state, gr_nes_mapper id, uint8_t prg_banks, gr_nes_io_write_fn io_write, void *io_user);
```

#### `gr_nes_mapper_runtime_init_layout`

```c
gr_result gr_nes_mapper_runtime_init_layout(gr_nes_mapper id, uint8_t prg_banks, gr_nes_io_write_fn io_write, void *io_user);
```

#### `gr_nes_mapper_runtime_id`

```c
gr_nes_mapper gr_nes_mapper_runtime_id(void);
```

#### `gr_nes_mapper_prg_banks`

```c
gr_bank_set *gr_nes_mapper_prg_banks(void);
```

#### `gr_nes_mapper_chr_banks`

```c
gr_bank_set *gr_nes_mapper_chr_banks(void);
```

#### `gr_nes_prg_read`

  Copy bytes out of a data-only PRG bank into RAM. This helper runs from RAM on NES so it can switch R6/MMC1's window without swapping out its caller. `prg_bank` is a 16 KB file bank; `offset` is local to that bank.
```c
gr_result gr_nes_prg_read(uint8_t prg_bank, uint16_t offset, uint8_t *dst, uint16_t length);
```

### Types

#### `gr_nes_mapper_state`

```c
typedef struct { gr_nes_mapper id; gr_bank_set prg; gr_bank_set chr; gr_nes_io_write_fn io_write; void *io_user; uint8_t shift; /* MMC1 5-bit serial shift register */ uint8_t shift_count; /* bits accumulated so far (0..5) */ uint8_t bank_select; /* MMC3 $8000 latch */ } gr_nes_mapper_state;
```

### Constants and macros

#### `GR_NES_MAPPER_NROM`

  Opt-in NES mapper extension. NROM is the default; MMC1 and MMC3 expose real switchable bank sets whose writes are translated into mapper register sequences. See docs/banking.md.
```c
GR_NES_MAPPER_NROM
```

#### `GR_NES_MAPPER_MMC1`

  Opt-in NES mapper extension. NROM is the default; MMC1 and MMC3 expose real switchable bank sets whose writes are translated into mapper register sequences. See docs/banking.md.
```c
GR_NES_MAPPER_MMC1
```

#### `GR_NES_MAPPER_MMC3`

  Opt-in NES mapper extension. NROM is the default; MMC1 and MMC3 expose real switchable bank sets whose writes are translated into mapper register sequences. See docs/banking.md.
```c
GR_NES_MAPPER_MMC3
```

#### `GR_NES_CHR_BANK4`

  Assets are placed in 8 KB CHR banks, while MMC1/MMC3 bank registers select 4 KB tables in the mode Gramma programs. Each 8 KB bank mirrors its first 4 KB table into the second, so either half selects the same tiles.
```c
#define GR_NES_CHR_BANK4(bank_8k) ((uint16_t)((bank_8k) * 2u))
```

## system {#gramma-target-nes-system}

Header: [`gramma/target/nes/system.h`](../../core/include/gramma/target/nes/system.h).

### Functions

#### `gr_nes_system_query`

  Fill *out with NES capabilities. Returns GR_ERR_UNSUPPORTED elsewhere.
```c
gr_result gr_nes_system_query(gr_nes_system_caps *out);
```

### Types

#### `gr_nes_system_caps`

```c
typedef struct { uint8_t tile_bytes; uint8_t bpp; uint8_t palette_colors; uint8_t palette_slots; uint8_t players; uint16_t screen_w; uint16_t screen_h; uint8_t nametable_w; uint8_t nametable_h; const char *name; } gr_nes_system_caps;
```

### Constants and macros

#### `GR_NES_TILE_BYTES`

  Opt-in NES system information. Values describe the stock 2C02 PPU: 32x30 tile nametables (two physical tables with horizontal/vertical mirroring, four with NROM four-screen), 8x8 2bpp background/sprite tiles and two serial controllers. Mapper banks remain in the separate target/nes/mapper.h extension.
```c
#define GR_NES_TILE_BYTES      16u
```

#### `GR_NES_TILE_BPP`

```c
#define GR_NES_TILE_BPP        2u
```

#### `GR_NES_PALETTE_COLORS`

```c
#define GR_NES_PALETTE_COLORS  4u
```

#### `GR_NES_PALETTE_SLOTS`

```c
#define GR_NES_PALETTE_SLOTS   8u
```

#### `GR_NES_PLAYERS`

```c
#define GR_NES_PLAYERS         2u
```

#### `GR_NES_SCREEN_W`

```c
#define GR_NES_SCREEN_W        256u
```

#### `GR_NES_SCREEN_H`

```c
#define GR_NES_SCREEN_H        240u
```

#### `GR_NES_NAMETABLE_W`

```c
#define GR_NES_NAMETABLE_W     32u
```

#### `GR_NES_NAMETABLE_H`

```c
#define GR_NES_NAMETABLE_H     30u
```

## SMS/GG mapper (target/sms/mapper.h) {#gramma-target-sms-mapper}

Header: [`gramma/target/sms/mapper.h`](../../core/include/gramma/target/sms/mapper.h).

### Functions

#### `gr_sms_mapper_init`

  Initialise a mapper state. A two-bank ROM has no switchable slot.
```c
gr_result gr_sms_mapper_init(gr_sms_mapper_state *state, uint8_t rom_banks, gr_sms_bank_write_fn write, void *user);
```

#### `gr_sms_mapper_runtime_init`

  Runtime mapper installed by the SMS backend from the build-time layout.
```c
gr_result gr_sms_mapper_runtime_init(uint8_t rom_banks, gr_sms_bank_write_fn write, void *user);
```

#### `gr_sms_mapper_rom_bank_count`

```c
uint8_t gr_sms_mapper_rom_bank_count(void);
```

#### `gr_sms_mapper_rom_banks`

```c
gr_bank_set *gr_sms_mapper_rom_banks(void);
```

### Types

#### `gr_sms_mapper_state`

```c
typedef struct { uint8_t rom_banks; gr_sms_bank_write_fn write; void *user; gr_bank_set rom; } gr_sms_mapper_state;
```

### Constants and macros

#### `GR_SMS_MIN_ROM_BANKS`

  Opt-in SMS slot-2 ROM banking. This header is intentionally not included by gramma.h. Bank 0 and bank 1 are fixed at $0000-$7FFF; the 16 KB slot at $8000-$BFFF is switched by writing the Sega mapper register at $FFFF. Logical banks follow the physical ROM bank numbers used by devkitSMS, so bank 2 is the first switchable bank. The build injects GR_SMS_ROM_BANKS from [mapper.sms] in project.toml.
```c
#define GR_SMS_MIN_ROM_BANKS 2u
```

#### `GR_SMS_MAX_ROM_BANKS`

```c
#define GR_SMS_MAX_ROM_BANKS 64u
```

#### `GR_SMS_DEFAULT_BANK`

```c
#define GR_SMS_DEFAULT_BANK  2u
```

## system {#gramma-target-sms-system}

Header: [`gramma/target/sms/system.h`](../../core/include/gramma/target/sms/system.h).

### Functions

#### `gr_sms_system_query`

  Fill *out with SMS/GG capabilities. Returns GR_ERR_UNSUPPORTED elsewhere.
```c
gr_result gr_sms_system_query(gr_sms_system_caps *out);
```

### Types

#### `gr_sms_system_caps`

```c
typedef struct { uint8_t tile_bytes; uint8_t bpp; uint8_t palette_colors; uint8_t palette_slots; uint8_t players; uint16_t screen_w; uint16_t screen_h; uint16_t sprite_tile_base; const char *name; } gr_sms_system_caps;
```

### Constants and macros

#### `GR_SMS_TILE_BYTES`

  Opt-in Master System / Game Gear information. The VDP uses 4bpp planar tiles: 32 bytes per 8x8 tile, 16 CRAM colours per palette and sprite tiles start at VRAM tile 256. The console build flag TARGET_GG is not needed to query capabilities; both systems share these values.
```c
#define GR_SMS_TILE_BYTES        32u
```

#### `GR_SMS_TILE_BPP`

```c
#define GR_SMS_TILE_BPP          4u
```

#### `GR_SMS_PALETTE_COLORS`

```c
#define GR_SMS_PALETTE_COLORS    16u
```

#### `GR_SMS_PALETTE_SLOTS`

```c
#define GR_SMS_PALETTE_SLOTS     2u
```

#### `GR_SMS_PLAYERS`

```c
#define GR_SMS_PLAYERS           2u
```

#### `GR_SMS_SCREEN_W`

```c
#define GR_SMS_SCREEN_W          256u
```

#### `GR_SMS_SCREEN_H`

```c
#define GR_SMS_SCREEN_H          192u
```

#### `GR_SMS_SPRITE_TILE_BASE`

```c
#define GR_SMS_SPRITE_TILE_BASE  256u
```

## Target limits and fixed-point helpers (target.h) {#gramma-target}

Header: [`gramma/target.h`](../../core/include/gramma/target.h).

### Functions

#### `gr_itof`

  Fixed-point helpers live in the core so they can be shared by backends.
```c
#if defined(GRAMMA_TARGET_GB) # define GR_SCREEN_W 160 # define GR_SCREEN_H 144 #elif defined(GRAMMA_TARGET_NES) # define GR_SCREEN_W 256 # define GR_SCREEN_H 240 #elif defined(GRAMMA_TARGET_SMS) # define GR_SCREEN_W 256 # define GR_SCREEN_H 192 #else # define GR_SCREEN_W 256 # define GR_SCREEN_H 224 #if defined(GRAMMA_TARGET_GB) # define GR_PAD_PLAYERS 1 #else # define GR_PAD_PLAYERS 2 gr_fixed gr_itof(int value);
```

#### `gr_ftoi`

```c
int gr_ftoi(gr_fixed value);
```

#### `gr_fmul`

```c
gr_fixed gr_fmul(gr_fixed a, gr_fixed b);
```

#### `gr_fdiv`

```c
gr_fixed gr_fdiv(gr_fixed a, gr_fixed b);
```

#### `gr_fclamp`

```c
gr_fixed gr_fclamp(gr_fixed value, gr_fixed lo, gr_fixed hi);
```

### Constants and macros

#### `GR_FIXED_ONE`

```c
#define GR_FIXED_ONE       ((gr_fixed)(1L << GR_FIXED_SHIFT))
```

#### `GR_BUTTON_BIT`

```c
#define GR_BUTTON_BIT(b)   ((uint16_t)1u << (uint16_t)(b))
```

## Public types (types.h) {#gramma-types}

Header: [`gramma/types.h`](../../core/include/gramma/types.h).

### Types

#### `gr_color`

  15-bit RGB, the common visual language of retro hardware.
```c
typedef uint16_t gr_color;
```

#### `gr_tileset`

  A tileset is packed 8x8 tiles in row-major order, MSB-first within a byte. Index 0 is transparent. Generated by the asset pipeline from a PNG.
```c
typedef struct { uint16_t tile_count; uint8_t bpp; const uint8_t *tiles; const gr_color *palette; uint8_t palette_size; } gr_tileset;
```

#### `gr_map`

  Row-major 8x8 tile indices, generated from a PNG background or Tiled map.
```c
typedef struct { uint16_t width; /* in tiles */ uint16_t height; /* in tiles */ const uint16_t *tiles; } gr_map;
```

#### `gr_bg`

  Optional NES-style extensions, ignored by targets without the hardware: nametable  - which 8 KB PPU nametable to render from (0..3) palette_map - one background palette index (0..3) per map tile; when NULL the whole background uses pal_slot.
```c
typedef struct { const gr_tileset *tileset; const gr_map *map; uint8_t pal_slot; int16_t scroll_x; int16_t scroll_y; bool visible; uint8_t nametable; const uint8_t *palette_map; } gr_bg;
```

#### `gr_sprite`

```c
typedef struct { const gr_tileset *tileset; uint8_t pal_slot; uint8_t frame; uint8_t frame_w; /* frame size in tiles */ uint8_t frame_h; uint8_t flip; /* GR_FLIP_X | GR_FLIP_Y */ bool visible; int16_t x; int16_t y; } gr_sprite;
```

#### `gr_actor`

```c
typedef struct gr_actor gr_actor;
```

#### `gr_actor_def`

```c
typedef struct { const char *name; const gr_tileset *tileset; gr_fixed x; gr_fixed y; gr_fixed vx; gr_fixed vy; uint8_t pal_slot; uint8_t frame_w; uint8_t frame_h; uint8_t frame; gr_actor_update_fn update; void *userdata; } gr_actor_def;
```

#### `gr_pcm`

  Small PCM blob, emitted by the pipeline from a WAV file.
```c
typedef struct { uint16_t sample_rate; uint16_t length; const int8_t *data; } gr_pcm;
```

#### `gr_dmc`

  4-bit delta-modulated sample for the NES APU DMC channel. `rate` is the hardware rate index (0 = ~4.2 kHz, 15 = ~33 kHz). Generated by the pipeline from the same WAV as gr_pcm; other targets can ignore it.
```c
typedef struct { uint8_t rate; uint16_t length; /* bytes, padded to a multiple of 16 */ const uint8_t *data; bool loop; } gr_dmc;
```

#### `gr_note`

  One 16th-note. freq_hz == 0 is a rest. channel selects a mixer channel.
```c
typedef struct { uint16_t freq_hz; uint16_t ticks; uint8_t volume; uint8_t channel; gr_wave wave; } gr_note;
```

#### `gr_song`

  Optional SN76489 PSGlib-format stream for SMS/Game Gear. Generated by the music compiler; NULL for hand-written songs and other targets.
```c
typedef struct { uint16_t bpm; uint16_t note_count; const gr_note *notes; bool loop; const uint8_t *psg; } gr_song;
```

### Constants and macros

#### `GR_OK`

  Portable result codes. Positive values keep enum conversions safe on 8-bit.
```c
GR_OK
```

#### `GR_ERR_INVALID_ARG`

  Portable result codes. Positive values keep enum conversions safe on 8-bit.
```c
GR_ERR_INVALID_ARG
```

#### `GR_ERR_NO_MEMORY`

  Portable result codes. Positive values keep enum conversions safe on 8-bit.
```c
GR_ERR_NO_MEMORY
```

#### `GR_ERR_UNSUPPORTED`

  Portable result codes. Positive values keep enum conversions safe on 8-bit.
```c
GR_ERR_UNSUPPORTED
```

#### `GR_ERR_BACKEND`

  Portable result codes. Positive values keep enum conversions safe on 8-bit.
```c
GR_ERR_BACKEND
```

#### `GR_ERR_NOT_FOUND`

  Portable result codes. Positive values keep enum conversions safe on 8-bit.
```c
GR_ERR_NOT_FOUND
```

#### `GR_PLAYER_1`

```c
GR_PLAYER_1
```

#### `GR_PLAYER_2`

```c
GR_PLAYER_2
```

#### `GR_PLAYER_COUNT`

```c
GR_PLAYER_COUNT
```

#### `GR_BTN_UP`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_UP
```

#### `GR_BTN_DOWN`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_DOWN
```

#### `GR_BTN_LEFT`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_LEFT
```

#### `GR_BTN_RIGHT`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_RIGHT
```

#### `GR_BTN_A`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_A
```

#### `GR_BTN_B`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_B
```

#### `GR_BTN_X`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_X
```

#### `GR_BTN_Y`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_Y
```

#### `GR_BTN_L`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_L
```

#### `GR_BTN_R`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_R
```

#### `GR_BTN_START`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_START
```

#### `GR_BTN_SELECT`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_SELECT
```

#### `GR_BTN_COUNT`

  Canonical pad. Games declare which buttons they need at build time.
```c
GR_BTN_COUNT
```

#### `GR_RGB`

```c
#define GR_RGB(r, g, b) ((gr_color)((uint16_t)(((uint16_t)(r) & 0x1f) << 10) | \
```

#### `GR_FLIP_X`

```c
#define GR_FLIP_X 0x01u
```

#### `GR_FLIP_Y`

```c
#define GR_FLIP_Y 0x02u
```

#### `GR_WAVE_SQUARE`

```c
GR_WAVE_SQUARE
```

#### `GR_WAVE_TRIANGLE`

```c
GR_WAVE_TRIANGLE
```

#### `GR_WAVE_SAW`

```c
GR_WAVE_SAW
```

#### `GR_WAVE_NOISE`

```c
GR_WAVE_NOISE
```

#### `GR_WAVE_PCM`

```c
GR_WAVE_PCM
```
