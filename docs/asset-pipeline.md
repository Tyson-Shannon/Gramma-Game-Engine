# Asset pipeline

The pipeline runs at build time on the host. It emits C arrays into
`<project>/generated/<target>/` plus a `manifest.json` and a generated
`meson.build`. No converter or interpreter ships on the console.

## project.toml

```toml
[project]
name = "test-kart"
default_target = "pc"
max_sprites = 2
width = 256
height = 224

[[image]]
name = "kart"                # -> const gr_tileset kart_tileset
file = "assets/kart.png"
kind = "sprite"              # or "background" (also emits gr_map)
bpp = 4
frame_width = 16             # sprite frame size in pixels
frame_height = 16

[[audio]]
name = "engine"              # -> const gr_sfx_def engine_sfx
file = "assets/engine.wav"
sample_rate = 22050

[budgets.pc]
rom_kb = 512
vram_tiles = 1024

[target.gb.image.kart]       # per-target overrides
bpp = 2

[target.nes.image.kart]
bpp = 2                      # NES CHR is 2bpp planar

[budgets.nes]
rom_kb = 32                  # asset data budget, not total cartridge size
vram_tiles = 512

[mapper.nes]
id = "mmc3"                  # nrom | mmc1 | mmc3
prg_banks = 4                # 16 KB banks
chr_banks = 2                # 8 KB banks

[mapper.gb]
id = "mbc1"                  # none | mbc1 | mbc3 | mbc5
rom_banks = 4                # 16 KB banks, including fixed bank 0
ram_banks = 0                # 8 KB SRAM banks

[target.sms.image.kart]      # SMS uses 4bpp planar tiles by default
bpp = 4

[budgets.sms]
rom_kb = 64                  # total Sega mapper ROM size
vram_tiles = 512

[mapper.sms]
rom_banks = 4                # 16 KB banks, including fixed banks 0/1

[grain]
sources = ["src/game.grain"] # or omit to auto-discover src/*.grain
```

`generate()` also transpiles each `[grain].sources` file into
`generated/<target>/grain_<stem>.c` and adds it to `generated_sources`. Grain
sources use the asset names declared by `[[image]]`/`[[audio]]` through
`extern` declarations, so language code and converted assets are compiled by
the same build. See [`grain.md`](grain.md).

PNG dimensions must be multiples of 8. Index 0 is reserved for transparency;
the remaining colours are chosen from the most frequent opaque colours, capped
at `2^bpp`. A build fails if the target cannot represent the requested bpp or
palette size.

## Tile packing

- **chunky** (PC, GBA, Genesis): rows of MSB-first interleaved pixels, e.g.
  two 4bpp pixels per byte.
- **planar** (GB, NES, SMS, SNES): one bit-plane per 8-byte row, which is the
  native CHR layout of those PPU families.

Tiles are deduplicated per image before packing. Backgrounds additionally emit
a row-major `gr_map` of tile indices.

### NES CHR layout

`generate()` emits an 8 KB-per-bank `nes_chr_data` object for the NES. The bank
count comes from `[mapper.nes]` (`chr_banks = 1, 2, 4 ... 16` for mmc1/mmc3;
nrom stays at 1), and the build driver enlarges the cc65 `ROM2` segment to
match. The bytes are written as `chr.s` into that segment instead of a C array,
because cc65 rejects arrays over 64 KB; C tilesets still reference
`extern const uint8_t nes_chr_data[]`. Each 8 KB bank holds one 4 KB tile table
followed by an identical copy. Both PPU pattern tables therefore contain the
same tiles, so fetches do not depend on PPUCTRL's pattern-table bits.

Images can be pinned to a bank and local tile index:

```toml
[[image]]
name = "altkart"
file = "assets/altkart.png"
bpp = 4

[target.nes.image.altkart]
bpp = 2
chr_bank = 1
chr_tile = 4
```

Tile indices are local to one 4 KB table (0-255). Explicit placements are
packed first; remaining backgrounds start at tile 0 and sprites at tile 4 in
their assigned bank, preserving the one-bank layout. Overlaps, negative or
overflowing tile ranges and banks outside `chr_banks` fail the build. The
manifest records `chr_banks` plus each image's `chr_bank`/`chr_tile`, and
generated tilesets point at `nes_chr_data + (bank * 512 + tile) * 16` (for
example `nes_chr_data + 64` for `test-kart`'s bank 0/tile 4 sprites). A
generated `nes_font.s` exports `NESfont` absolutely to satisfy cc65's forced
font import without spending CHR space.

### Game Boy bank placement

Generated GB image and audio C files start with `#pragma bank 1`. Keeping large
generated arrays out of fixed code leaves GBDK's banked-call helpers
(`___sdcc_call_hl` and `___sdcc_bcall_ehl`) below `$4000`; in the shipped debug
map `_HOME` ends at `$2C21` and those helpers sit at `$2E6E`/`$2E92`. The example
also provides a small `BANKED` helper in bank 2 that returns `0x5a`, so its MBC
probe reads real switchable ROM rather than a patched temporary array.

`[mapper.gb]` selects the GBDK cart type (`-Wl-yt`), ROM bank count (`-Wl-yo`)
and SRAM bank count (`-Wm-ya`). `gr check` validates the mapper ID, power-of-two
ROM banks and per-mapper caps (32 on MBC1, 128 on MBC3/MBC5) and SRAM caps
(none for plain ROM, 4 banks on MBC1/MBC3, 16 on MBC5). `gr check/build/run`
accept `--gb-mapper`, `--gb-rom-banks` and `--gb-ram-banks` overrides.

### SMS bank placement

SMS images stay 4bpp planar (32 bytes per 8x8 tile) and are emitted as ordinary
SDCC C arrays. Source files under `src/sms/` named `bankN_*.c` compile with
`--constseg BANKN`; the linker places `BANK2..BANK(N-1)` at
`$8000 + bank * 0x10000`, i.e. the switchable 16 KB slot viewed through the
Sega mapper. Files naming a bank outside `[mapper.sms] rom_banks` are skipped
with a build note, so the same project also builds a fixed two-bank ROM.

`targets/sms/src/sms_header.c` emits the 16-byte `TMR SEGA` header at `$7FF0`.
The region nibble is `4` for export Master System and `7` for Game Gear; the
size nibble comes from the bank count. `makesms` pads the ROM to a 16 KB
multiple and updates the checksum at `$7FFA`. CI checks the size, region/size
byte, checksum and the `0x5a`/`0x3c` sentinels in banks 2/3 of the shipped
example.

## Audio

WAV input must be 8- or 16-bit mono/stereo PCM. It is resampled to the
requested rate, converted to signed 8-bit and capped at 16,384 samples. The
emitted `gr_sfx_def` uses `GR_WAVE_PCM`; on the PC backend the samples play
directly, while GB, NES and SMS approximate them with tones until sample playback
is wired up per target. SMS uses a small SN76489 tone sequencer, not PSGlib
tracker data.

Music is authored as C `gr_note` arrays (16th-note ticks, frequency, volume,
wave, channel) and compiled by the toolchain. A tracker-style music compiler is
planned for Phase 3.

## Budget linter

`gr check --target <name>` validates:

- bpp support and palette size for every image,
- nametable tile limit for backgrounds (960 tiles for a single NES nametable),
- total unique tiles against VRAM,
- live sprite count and per-scanline limit,
- generated asset bytes against the ROM limit,
- NES mapper ID, power-of-two PRG count (2..16 on MMC1/MMC3, 2 on NROM),
  power-of-two CHR count (up to 16), per-image bank/tile ranges and the
  256-tile capacity of each CHR bank.
- Game Boy mapper ID, power-of-two ROM/SRAM bank counts and per-mapper caps.
- SMS power-of-two ROM bank count (2..64), the ROM-size header code and that the
  declared layout fits `budgets.sms.rom_kb`.

Errors are printed with `error:` prefixes and fail the build. This is a core
feature: hardware limits are enforced before a ROM is ever flashed.
