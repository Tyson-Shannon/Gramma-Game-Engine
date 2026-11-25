# Banking and overlay abstraction

Bank switching is an opt-in extension. The portable base API in `gramma.h`
stays a lowest-common-denominator contract; games that need mapper hardware
include a target header explicitly.

## Generic bank sets

Public header: [`core/include/gramma/bank.h`](../core/include/gramma/bank.h).

```c
#include <gramma/bank.h>

typedef void (*gr_bank_write_fn)(uint8_t slot, uint16_t bank, void *user);

typedef struct {
    uint8_t          slot_count;
    uint16_t         current[GR_BANK_MAX_SLOTS];
    gr_bank_write_fn write;   /* NULL for software-only bank sets */
    void            *user;
} gr_bank_set;

gr_result gr_bank_set_init(gr_bank_set *set, uint8_t slot_count,
                           gr_bank_write_fn write, void *user);
gr_result gr_bank_select(gr_bank_set *set, uint8_t slot, uint16_t bank);
uint8_t   gr_bank_slots(const gr_bank_set *set);
uint16_t  gr_bank_current(const gr_bank_set *set, uint8_t slot);
```

A `gr_bank_set` models a group of logical windows. The core caches the selected
bank for every slot and calls the backend's `write` callback when one is
supplied. A set with `slot_count == 0` describes fixed ROM: every `select()`
call is rejected with `GR_ERR_INVALID_ARG` before any hardware is touched.

This layer deliberately does not know about mapper registers. The backend
owns those writes, so the same API describes NES PRG/CHR banks, Game Boy MBC
banks and the Sega slot-2 ROM window on SMS/Game Gear.

For the common "two versions of the same tile indices" case, `gr_bank_switch`
caches the pair and removes the current-bank bookkeeping from game code:

```c
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

`init()` selects `bank_a`; `toggle()` selects the other bank and returns the new
value, and `reset()` returns to `bank_a`. The shipped `test-kart` example uses
this helper to flip MMC3 CHR slot 2 when B is pressed.

## Game Boy MBC extension

Public header:
[`core/include/gramma/target/gb/mapper.h`](../core/include/gramma/target/gb/mapper.h).

```c
#include <gramma/target/gb/mapper.h>

typedef enum {
    GR_GB_MAPPER_NONE = 0,
    GR_GB_MAPPER_MBC1 = 1,
    GR_GB_MAPPER_MBC3 = 3,
    GR_GB_MAPPER_MBC5 = 5
} gr_gb_mapper;

typedef void (*gr_gb_bank_write_fn)(uint8_t kind, uint16_t bank, void *user);

#define GR_GB_BANK_ROM 0u
#define GR_GB_BANK_RAM 1u

gr_result gr_gb_mapper_init(gr_gb_mapper_state *state, gr_gb_mapper id,
                            uint8_t rom_banks, uint8_t ram_banks,
                            gr_gb_bank_write_fn write, void *user);
gr_gb_mapper gr_gb_mapper_runtime_id(void);
uint8_t   gr_gb_mapper_rom_bank_count(void);
uint8_t   gr_gb_mapper_ram_bank_count(void);
gr_bank_set *gr_gb_mapper_rom_banks(void);
gr_bank_set *gr_gb_mapper_ram_banks(void);
```

A plain 32 KB cartridge has no switchable windows. MBC1/MBC3/MBC5 add one
16 KB ROM window at `$4000-$7FFF` and, when the cartridge has SRAM, one 8 KB
RAM window at `$A000-$BFFF`. Bank 0 stays fixed at `$0000-$3FFF`, so logical
ROM banks are 1..`rom_banks-1`. MBC1 supports at most 32 ROM banks; MBC3/MBC5
support 128. SRAM is capped at four 8 KB banks on MBC1/MBC3 and 16 on MBC5.

The backend installs the build-time layout in `gr_init()` with real `SWITCH_ROM`
/ `SWITCH_RAM` writes, so games can use the runtime accessors immediately.
`gr_gb_mapper_init()` takes an injected writer for unit tests. The shipped
example places a `BANKED` sentinel in ROM bank 2; GBDK's trampoline saves and
restores the switchable window from fixed code, so the probe does not patch a
temporary ROM or leave switchable code mapped while interrupts run.

```toml
[mapper.gb]
id = "mbc1"        # none | mbc1 | mbc3 | mbc5
rom_banks = 4      # 16 KB banks, including fixed bank 0
ram_banks = 0      # 8 KB SRAM banks
```

`gr check`, `gr build` and `gr run` accept `--gb-mapper`, `--gb-rom-banks` and
`--gb-ram-banks` overrides. The build driver maps these to GBDK's `-Wl-yt`,
`-Wl-yo` and `-Wm-ya` flags plus `GR_GB_*` compile definitions.

## SMS / Game Gear mapper extension

Public header:
[`core/include/gramma/target/sms/mapper.h`](../core/include/gramma/target/sms/mapper.h).

```c
#include <gramma/target/sms/mapper.h>

#define GR_SMS_MIN_ROM_BANKS 2u
#define GR_SMS_MAX_ROM_BANKS 64u
#define GR_SMS_DEFAULT_BANK  2u

typedef void (*gr_sms_bank_write_fn)(uint16_t bank, void *user);

typedef struct {
    uint8_t              rom_banks;
    gr_sms_bank_write_fn write;
    void                *user;
    gr_bank_set          rom;
} gr_sms_mapper_state;

gr_result gr_sms_mapper_init(gr_sms_mapper_state *state, uint8_t rom_banks,
                             gr_sms_bank_write_fn write, void *user);
gr_result gr_sms_mapper_runtime_init(uint8_t rom_banks,
                                     gr_sms_bank_write_fn write, void *user);
uint8_t   gr_sms_mapper_rom_bank_count(void);
gr_bank_set *gr_sms_mapper_rom_banks(void);
```

Banks 0 and 1 are fixed at `$0000-$7FFF`; one slot switches banks 2..N-1 into
the 16 KB window at `$8000-$BFFF` by writing the Sega mapper register at
`$FFFF`. Logical banks match devkitSMS physical bank numbers, so bank 2 is the
first switchable bank. A two-bank ROM has zero slots and never writes `$FFFF`.
`gr_sms_mapper_init()` accepts an injected writer for unit tests;
`gr_init()` installs the runtime state with SMSlib's `SMS_mapROMBank()`.

```toml
[mapper.sms]
rom_banks = 4          # 16 KB banks: 2, 4, 8 ... 64
```

`gr check` validates the power-of-two count against the 1 MB cap and the
`[budgets.sms] rom_kb` limit. `gr build/check/run` accept `--sms-rom-banks`.
The build emits a SEGA header whose region/size byte follows the bank count,
compiles `bankN_*.c` into `BANKN` linker segments, and verifies the bank
sentinels in CI with `tests/sms_rom_check.py`.

## Vblank overlays

Public header: [`core/include/gramma/overlay.h`](../core/include/gramma/overlay.h).

```c
#include <gramma/overlay.h>

#define GR_OVERLAY_MAX_OPS     8u
#define GR_OVERLAY_TILE_BYTES  256u
#define GR_OVERLAY_MAP_BYTES   64u

gr_result gr_overlay_tiles(uint8_t dest, const uint8_t *src, uint16_t bytes,
                           bool sprite);
gr_result gr_overlay_nametable(uint8_t x, uint8_t y, uint8_t w, uint8_t h,
                               const uint8_t *tiles);
```

Staging copies the source bytes into a small work-RAM queue immediately, so the
caller can restore a bank or reuse a stack buffer before vblank. Backends apply
the queue from their frame-end handler; games normally do not call
`gr_overlay_flush()` themselves. On GB and SMS, both operations upload to VRAM
after the vblank wait. On NES, CHR lives in ROM so `gr_overlay_tiles()` returns
`GR_ERR_UNSUPPORTED`; bank switching is the supported way to change tile art,
and nametable patches are limited to 64 PPU writes per vblank. SMS tile uploads
are 32 bytes per 4bpp tile and sprite art must target VRAM tile 256 or higher.

The shipped GB example stages an alternate kart tileset at tile 64 and patches
an 8x8 nametable region when B is pressed. SMS stages the same art at tile 256
and patches a 4x2 tile region; NES uses the generic CHR bank switch for the
same button, so one source tree produces the appropriate behavior per target.

## NES mapper extension

Public header:
[`core/include/gramma/target/nes/mapper.h`](../core/include/gramma/target/nes/mapper.h).

```c
#include <gramma/target/nes/mapper.h>

typedef enum {
    GR_NES_MAPPER_NROM = 0,
    GR_NES_MAPPER_MMC1 = 1,
    GR_NES_MAPPER_MMC3 = 4
} gr_nes_mapper;

typedef void (*gr_nes_io_write_fn)(uint16_t address, uint8_t value, void *user);

typedef struct {
    gr_nes_mapper      id;
    gr_bank_set        prg;
    gr_bank_set        chr;
    gr_nes_io_write_fn io_write;
    void              *io_user;
    /* MMC1 shift register / MMC3 bank-select latch */
    uint8_t            shift, shift_count, bank_select;
} gr_nes_mapper_state;

gr_result gr_nes_mapper_init(gr_nes_mapper_state *state, gr_nes_mapper id);
gr_result gr_nes_mapper_init_hw(gr_nes_mapper_state *state, gr_nes_mapper id,
                                gr_nes_io_write_fn io_write, void *io_user);
gr_result gr_nes_mapper_init_hw_layout(gr_nes_mapper_state *state,
                                       gr_nes_mapper id, uint8_t prg_banks,
                                       gr_nes_io_write_fn io_write,
                                       void *io_user);
void      gr_nes_mapper_register_write(gr_nes_mapper_state *state,
                                       uint16_t address, uint8_t value);
gr_result gr_nes_mapper_runtime_init_layout(gr_nes_mapper id,
                                            uint8_t prg_banks,
                                            gr_nes_io_write_fn io_write,
                                            void *io_user);
gr_result gr_nes_prg_read(uint8_t prg_bank, uint16_t offset,
                          uint8_t *dst, uint16_t length);
```

`gr_nes_mapper_init()` is software-only and still supports NROM exclusively:
zero PRG/CHR slots, no hardware writes. `gr_nes_mapper_init_hw()` supplies a
low-level register writer and installs the mapper's bank writers. The
`_layout` variants take the 16 KB PRG bank count so startup registers select the
final code banks. The NES backend calls
`gr_nes_mapper_runtime_init_layout()` during `gr_init()` with the mapper and
layout configured in `project.toml`, so games can use the bank set immediately.

### MMC1 writer

- PRG: one 16 KB window. `gr_bank_select()` clocks five serial bits into the
  PRG register at `$A000`.
- CHR: two 4 KB windows, committed to `$B000` (slot 0) and `$C000` (slot 1).
- Writes to `$8000-$9FFF` with bit 7 set reset the shift register; the fifth
  following bit clocks the value into the register selected by the address
  range. Init programs control `$1C | mirror bits`: 2 = vertical, 3 =
  horizontal mirroring, 16 KB PRG mode, 4 KB CHR mode.

### MMC3 writer

- PRG: two 8 KB windows mapped to registers R6/R7.
- CHR: four logical slots mapped to R0-R3. Every bank-select write sets bit 7
  of `$8000`, selecting 4 KB CHR mode; init also programs R4/R5 so the rest of
  the pattern tables are defined. Runtime slot 2 (R2) was verified to control
  the sprite pattern table used by 8x8 sprites.
- Each bank write emits `$8000` = register index followed by `$8001` = bank
  value. Init writes the configured mirroring bit to `$A000` (0 = vertical,
  1 = horizontal) and disables IRQs (`$E000`); PRG mode 0 is bit 6 clear in the
  `$8000` writes.

## Project configuration

`project.toml` describes the cartridge layout under `[mapper.nes]`:

```toml
[mapper.nes]
id = "mmc3"        # nrom | mmc1 | mmc3
prg_banks = 4      # 16 KB PRG banks: 2, 4, 8 ... 16 on mmc1/mmc3
chr_banks = 2      # 8 KB CHR banks: 1, 2, 4 ... 16 on mmc1/mmc3
mirroring = "vertical"  # horizontal | vertical | four-screen (NROM only)
```

`mirroring` sets the iNES header bit (horizontal 0, vertical 1, four-screen 8)
and the startup mapper register value. Four-screen needs a board with four
physical nametables, so it is rejected on MMC1/MMC3; those boards use their
mirroring registers and accept horizontal or vertical. Games select one of the
four logical nametables with `gr_bg_set_nametable()` and can split background
palettes with `gr_bg_set_palette_map()`; see [`api.md`](api.md#sprites-backgrounds-palettes).

`gr check --target nes` validates the ID, mirroring mode, power-of-two PRG counts
between 2 and 16 (up to 256 KB), power-of-two CHR counts up to 16 (128 KB),
NROM's two-bank PRG / one-bank CHR limits and each image's placement. CHR banks and local tile indices can be pinned globally or
per target:

```toml
[[image]]
name = "altkart"
file = "assets/altkart.png"
kind = "sprite"

[target.nes.image.altkart]
bpp = 2
chr_bank = 1       # second 8 KB bank
chr_tile = 4       # tile 4 inside that bank's 4 KB table
```

Tile indices are local to one 4 KB pattern table; each 8 KB bank mirrors its
first 4 KB into the second, so either 4 KB half selects the same tiles. The
pipeline rejects placements outside the configured bank count, negative or
overflowing tile ranges, and two assets claiming the same tile in one bank.
Without explicit `chr_tile`, backgrounds are packed from tile 0 and sprites
from tile 4 within their assigned bank, preserving the original default layout.

The build driver passes the mapper ID, bank counts and mirroring bit to ca65 as
`GR_NES_MAPPER`, `GR_NES_PRG_BANKS`, `GR_NES_CHR_BANKS` and `GR_NES_MIRROR`, which
drive both the header and startup mapper programming in
`targets/nes/src/nes_crt0.s`. It also writes a generated linker config for every
layout, giving generated DMC samples a 64-byte-aligned `DMC` segment: `ROM2` is
enlarged for CHR banks, while PRG layouts above 32 KB add data-only segments
`PRG0..PRG(n-3)`, keep main code in `ROMFIX` ($C000-$FFFF), link `overlay.c`
into a `CODE2` segment in the switchable code bank, and copy a `RAMCODE`
routine into $7400. Generated CHR is emitted as `chr.s` into the CHR segment
rather than a C array, since cc65 cannot compile arrays over 64 KB.
Layouts above 15 PRG or CHR banks use a NES 2.0 header (byte 7 format bits,
bytes 8/9 size MSBs, byte 10 PRG RAM size); smaller layouts retain iNES.
`gr build/check/run --mapper`, `--prg-banks`, `--chr-banks` and `--mirroring`
override these values for one command without editing `project.toml`.

MMC3 startup deserves a note: `$E000` is IRQ disable, not mode control. Every
`$8000` bank-select write carries bit 7 (4 KB CHR mode) with bit 6 clear (PRG
mode 0), and R0-R7 are all programmed so both pattern tables are defined. With
`NES_CTRL = 0x90`, backgrounds read `$0000` and sprites read `$1000`; leaving
R1/R3/R4/R5 at their power-on values makes the background black. R7 is programmed to the last 8 KB code bank so `$A000-$BFFF` does not alias a
data bank. Bank 0's table is mirrored into both 4 KB halves of an 8 KB asset
bank, so consecutive 4 KB register values from the same asset bank render
identically.

## Runtime switching

`gr_init()` installs the build-time mapper into the NES backend with a real
hardware writer. Games include `gramma/target/nes/mapper.h` and use the runtime
accessors; the initialization is already done for them:

```c
#include <gramma/target/nes/mapper.h>

/* MMC3 CHR slot 2 controls the sprite pattern table in 4 KB mode.
 * GR_NES_CHR_BANK4(1) is 4 KB bank 2, i.e. the first half of 8 KB bank 1. */
(void)gr_bank_select(gr_nes_mapper_chr_banks(), 2u,
                     GR_NES_CHR_BANK4(1));
```

`gr_nes_mapper_runtime_id()` returns the configured mapper and
`gr_nes_mapper_prg_banks()` exposes PRG slots. Prefer CHR switching from running
code: MMC3 PRG windows hold the executing program, so writing R6/R7 can swap out
the caller. For data-only banks use `gr_nes_prg_read()`, which runs from RAM and
temporarily switches R6 (MMC3) or the lower window (MMC1). It disables NMI via a
shadow `$2000` value because that register is write-only, then restores both
the mapper window and PPUCTRL.

The generated CHR is emitted as mirrored 8 KB banks, so assets can share a local
tile index in different banks. The shipped `test-kart` places `kart` at bank
0/tile 4 and `altkart` at bank 1/tile 4. Pressing B toggles slot 2 between
`GR_NES_CHR_BANK4(0)` and `GR_NES_CHR_BANK4(1)`, changing 264 sprite pixels and
dropping the frame from six colors to three; a second press restores it
exactly. Asset banks are 8 KB; mapper registers select 4 KB halves, which is why
the macro doubles the bank index.

## Status and next steps

- **Done:** generic bank-set cache and two-bank helper, NROM state, MMC1/MMC3
  register writers with fake-IO unit tests, `[mapper.nes]` parsing and budget
  validation, mapper-aware ROM headers and startup programming for all three
  mappers, C-side runtime bank switching, larger CHR ROMs (up to 16 banks),
  larger PRG ROMs (up to 16 banks) with RAM-resident reads, bank-aware asset
  placement and a shipped two-bank example verified in `nes-py`.
- **Done:** Game Boy MBC1/MBC3/MBC5 ROM and SRAM bank sets with injected writer
  tests, `[mapper.gb]` parsing and GBDK cart flags, a bank-2 `BANKED` sentinel
  example, and the opt-in vblank overlay queue on GB and NES.
- **Done:** Sega slot-2 mapper state with injected writer tests, `[mapper.sms]`
  parsing and size-code validation, `BANKN` segment emission, a bank-2 sentinel
  example and SMS vblank overlays. CI checks SMS/GG ROM structure; rendered
  emulator and hardware bank probes are still pending.
- **Deferred:** physical-hardware validation is skipped for now; emulator CI
  remains the active gate for PC/GB/NES and structural ROM checks cover SMS/GG.
  See [`hardware-validation.md`](hardware-validation.md) for the manual checklist
  to run later.
- The NES custom NMI (see `targets/nes/src/nes_crt0.s`) handles fine scrolling.
  CHR bank switches are applied from game code; nametable overlays share the
  vblank write budget with the NMI's PPU updates.
