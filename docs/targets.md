# Targets

| Target | Status | Build driver | Native resolution |
|---|---|---|---|
| `pc` | working simulator | Meson + SDL2 | 256x224 (configurable) |
| `gb` | working ROM build | GBDK-2020 `lcc` | 160x144 |
| `nes` | working (cc65, NROM/MMC1/MMC3) | cc65 `cl65` | 256x240 |
| `sms` | working (SDCC + devkitSMS, Sega mapper; `--gg` for Game Gear) | SDCC `sdcc` + `makesms` | 256x192 |
| `genesis` | planned (Phase 3) | SGDK | 320x224 |
| `gba` | planned (Phase 3) | devkitARM | 240x160 |
| `snes` | planned (Phase 4) | PVSnesLib | 256x224 |

`gr targets` prints the live status; `gr check --target <name>` runs the
pipeline and budget linter without compiling.

## Budget profiles

Profiles live in [`pipeline/gramma_pipeline/targets.py`](../pipeline/gramma_pipeline/targets.py):
ROM size, VRAM tile count, palette size, sprite count, sprites per scanline and
nametable tile limit. Projects can override them in `project.toml`, e.g.:

```toml
[budgets.gb]
rom_kb = 32
vram_tiles = 384
```

## NES notes

- Build with `gr build --target nes`; cc65 is bootstrapped into
  `~/.cache/gramma/tools/cc65` on first use. `[mapper.nes]` in `project.toml`
  selects nrom, mmc1 or mmc3. MMC1/MMC3 may use 2, 4, 8 ... 16 PRG banks of
  16 KB and 1, 2, 4 ... 16 CHR banks of 8 KB; NROM is limited to two PRG and
  one CHR bank. `gr check` validates the layout and per-image placement, and
  `gr build/check/run` accept one-command `--mapper`, `--prg-banks` and
  `--chr-banks` overrides. The build driver emits the matching iNES header,
  startup mapper programming and a generated linker config for non-default
  layouts. `gr_init()` installs that mapper with a real hardware writer, so
  games can switch CHR banks at runtime through
  `gr_nes_mapper_chr_banks()`. The shipped `test-kart` defaults to MMC3 with two
  CHR banks and toggles sprite art with B; a four-bank MMC3 layout also renders
  and switches correctly. Both are checked in CI with `nes-py`. See
  [`banking.md`](banking.md).
- The pipeline emits N 8 KB CHR banks as `chr.s` in the cc65 `CHARS` segment
  (an assembly segment avoids cc65's 64 KB C-array limit). Each bank mirrors
  one 4 KB table into both pattern tables, so nametable and OAM indices do not
  depend on PPUCTRL selection. Images can be pinned with `chr_bank` and
  `chr_tile`; otherwise backgrounds start at tile 0 and sprites at tile 4
  within their bank. A generated `nes_font.s` exports `NESfont` absolutely to
  satisfy cc65's forced import without spending CHR space. Layouts above 15
  banks use a NES 2.0 header that also declares cc65's 8 KB PRG RAM; a 16-bank
  MMC3 ROM was smoke-tested in `nes-py`.
- For layouts above 32 KB, data-only banks are emitted as `PRG0..PRG(n-3)` and
  main executable code stays in `ROMFIX` ($C000-$FFFF). `overlay.c` links into a
  `CODE2` segment in the switchable code bank so `ROMFIX` still fits in 16 KB.
  `gr_nes_prg_read()` runs from `RAMCODE` at $7400 to copy bytes from a data bank
  without switching out the caller. The example includes a sentinel byte in
  `PRG0` and shifts its scroll by 8 pixels when the read succeeds.
- Asset banks are 8 KB but MMC1/MMC3 bank registers select 4 KB tables.
  `GR_NES_CHR_BANK4(n)` converts an asset bank to the register bank to pass to
  `gr_bank_select()`; the verified MMC3 sprite slot is 2.
- Backgrounds render from the selected `$2000`-`$23BF` nametable:
  `gr_bg_set_nametable()` chooses 0..3 and the build's mirroring mode
  (`[mapper.nes] mirroring = horizontal | vertical | four-screen`, or
  `--mirroring`) decides which physical tables those addresses reach. Four-screen
  is allowed only on NROM; MMC1/MMC3 use their mirroring registers. Without a
  palette map, the attribute table uses one background palette slot; with
  `gr_bg_set_palette_map()`, the backend packs four tiles' palette indices into
  each attribute byte so one nametable can mix palettes 0..3. Coarse scrolling
  rewrites nametable column 31 as the map scroll advances. A custom NMI
  (`targets/nes/src/nes_crt0.s`) writes the low three scroll bits from
  `$7EE0`/`$7EE1` to `$2005` and restores the `$2000` shadow so the selected
  nametable survives every vblank, despite cc65 2.19's stock NMI resetting
  `$2005`.
- Sprites are 8x8 OAM entries; a 2x2 actor frame uses four entries. Up to 64
  hardware sprites and 8 per scanline apply. OAM is staged at `$7F00` and sent
  with a hardware DMA write, avoiding slow `$2004` loops in the 2.19 NMI.
- RGB555 tile palettes are converted to the nearest 2C02 color and cached per
  palette slot. Music uses pulse/triangle/noise. A WAV SFX also carries a
  generated 4-bit DMC sample (`gr_sfx_def.dmc`): `gr_sfx_play()` starts it via
  `$4010`-`$4013` with the configured rate index and loop flag, from a
  64-byte-aligned `DMC` ROM segment. SFX without a DMC twin still fall back to a
  pulse tone. PC plays portable PCM directly; GB/SMS keep their tone fallback.
- Two eight-button controllers are read serially. X/Y/L/R are unavailable on
  this target. The example has been verified in `nes-py`, including sub-tile
  background shifts; physical hardware is untested.

## Game Boy notes

- One controller is addressable (`GR_PAD_PLAYERS == 1`); X/Y/L/R are not
  available. The example's second kart still runs as a non-input actor.
- The default build is a 64 KB MBC1 ROM; `[mapper.gb]` also supports `none`,
  `mbc3` and `mbc5`, with optional 8 KB SRAM banks. `gr check/build/run` accept
  `--gb-mapper`, `--gb-rom-banks` and `--gb-ram-banks` overrides, and the build
  driver emits the matching GBDK cart/ROM/RAM flags. MBC1 allows at most 32 ROM
  banks; MBC3/MBC5 allow 128. The shipped example's `BANKED` bank-2 probe returns
  `0x5a` from fixed code, and CI checks the `3e 5a c9` sentinel bytes.
- Tiles are 2bpp planar, palettes hold four DMG shades. Per-target asset
  overrides in `project.toml` re-encode the same PNGs for GB, and generated C
  files are placed in bank 1 with `#pragma bank 1` so GBDK's banked-call helpers
  remain in fixed code.
- Pressing B stages an alternate sprite tileset at tile 64 and an 8x8 nametable
  patch through the opt-in overlay queue. The GB backend applies both after
  `wait_vbl_done()`; PyBoy reports four idle colors and a 384-pixel change.
- Sprites are 8x8 hardware objects; an actor with a 2x2 tile frame uses four
  OAM entries. 40 OAM slots and a 10-sprites-per-line limit apply.
- Music plays as square tones on channel 1; PCM SFX are approximated on
  channel 2 with a short tone. This is intentionally a first-pass mapping:
  a target-aware music compiler is planned for later phases.

## SMS / Game Gear notes

- `gr build --target sms` uses SDCC 4.5.0 plus a pinned devkitSMS checkout;
  `gr` bootstraps both into `~/.cache/gramma`. Add `--gg` to link
  `SMSlib_GG.lib`, emit Game Gear palette words and write the Game Gear region
  code. The output is `build/test-kart-sms/game.sms` or `game.gg`.
- The native screen is 256x192 with a 32x28 tile nametable. Background tiles
  live at VRAM 0-255 and sprites at 256-511; `SMS_useFirstHalfTilesforSprites(0)`
  selects the upper half. 4bpp planar tiles are 32 bytes each. RGB555 colors
  convert to SMS `00BBGGRR` bytes or Game Gear 12-bit words; 16 colors are
  available per BG/sprite palette.
- Generated assets are plain SDCC C arrays. Banked data files named
  `bankN_*.c` compile with `--constseg BANKN` and link into
  `BANK2..BANK(N-1)` at `$8000-$BFFF`. A generated 16-byte SEGA header at
  `$7FF0` sets the region/size byte; `makesms` pads to 16 KB multiples and
  fills in the checksum.
- `[mapper.sms] rom_banks` accepts 2, 4, 8 ... 64 banks of 16 KB. Banks 0 and
  1 are fixed and one slot switches banks 2..N-1 through `$FFFF`.
  `gr check/build/run` accept `--sms-rom-banks`; a two-bank ROM is fixed and
  skips banked source files. The example probes `0x5a` in bank 2 when a mapper
  is present.
- Two SMS controllers are read through SMSlib. A/B map to buttons 1/2; START
  aliases button 1 on Master System (no dedicated START) and uses the real
  START bit on Game Gear. X/Y/L/R are unavailable. Sprites are 8x8 hardware
  objects with 64 slots and an 8-per-line limit; a 2x2 actor uses four.
- B presses stage an alternate sprite tileset at VRAM tile 256 and patch an
  8x8 nametable region through the opt-in overlay queue. VRAM writes are
  deferred to vblank. Hand-written songs use a small SN76489 tone sequencer on
  channel 0; songs from `[[music]]` carry an uncompressed PSGlib-format stream
  and are played by a built-in interpreter with three tone channels and one
  noise channel. Compressed PSG streams are not supported. Music and SFX share
  the PSG, so an SFX can temporarily override a music channel.
- CI checks ROM size, header signature, region/size byte, checksum and bank
  sentinels with `tests/sms_rom_check.py`. A maintained headless SMS emulator
  is not available in the CI image, so rendered-frame and hardware checks are
  still pending. See [`hardware-validation.md`](hardware-validation.md).

## PC notes

- Software renderer supports 1/2/4/8 bpp chunky tiles, palette slots, flip,
  scrolling/wrapping backgrounds and up to `GR_MAX_ACTORS` sprites.
- Four-channel synthesized audio (square/triangle/saw/noise/PCM).
- Keyboard + SDL game controllers map to the canonical pad.
