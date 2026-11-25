# Asset pipeline

The pipeline runs at build time on the host. It emits C arrays into
`<project>/generated/<target>/` plus a `manifest.json` and a generated
`meson.build`. No converter or interpreter ships on the console.

## project.toml

```toml
[project]
name = "test-kart"
schema_version = 1
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
dmc_rate = 15                # NES DMC rate index 0..15 (default 15)
dmc_loop = false             # NES DMC loop flag (default false)

[[music]]
name = "theme"               # -> const gr_song theme
file = "assets/theme.tick"   # text tracker score, see "Music" below

[[map]]
name = "level"               # -> const gr_tileset level_tileset + gr_map level_map
file = "assets/level.tmx"    # Tiled map, see "Tiled maps" below
layer = "ground"             # optional; first tile layer when omitted
bpp = 4

[budgets.pc]
rom_kb = 512
vram_tiles = 1024

[target.gb.image.kart]       # per-target overrides
bpp = 2

[target.gb.map.level]        # maps take the same bpp/CHR overrides
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
mirroring = "vertical"       # horizontal | vertical | four-screen (NROM only)

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

`schema_version` is optional for pre-version projects and defaults to 1; a
newer value fails with an explicit error instead of being guessed at. The
generated `manifest.json` carries its own `schema_version` plus an `artifacts`
object with absolute paths to the generated directory, manifest, `meson.build`
and every generated source. JSON Schema descriptions of the `[project]` table,
the manifest and the service contract live in [`schemas/`](../schemas/).

`generate()` also transpiles each `[grain].sources` file into
`generated/<target>/grain_<stem>.c` and adds it to `generated_sources`. Grain
sources use the asset names declared by
`[[image]]`/`[[audio]]`/`[[music]]`/`[[map]]` through `extern` declarations, so
language code and converted assets are compiled by the same build. v1 sources
may also declare typed locals, user functions and
fixed arrays; all of it is lowered to plain C before Meson sees the source list.
See [`grain.md`](grain.md).

PNG dimensions must be multiples of 8. Index 0 is reserved for transparency;
the remaining colours are chosen from the most frequent opaque colours, capped
at `2^bpp`. A build fails if the target cannot represent the requested bpp or
palette size.

## Tile packing

- **chunky** (PC, GBA, Genesis): rows of MSB-first interleaved pixels, e.g.
  two 4bpp pixels per byte.
- **planar** (GB, NES, SMS, SNES): one bit-plane per 8-byte row, which is the
  native CHR layout of those PPU families.

Tiles are deduplicated per image before packing. Backgrounds and imported maps
additionally emit a row-major `gr_map` of tile indices.

### Tiled maps

`[[map]]` imports one orthogonal tile layer from a Tiled `.tmx` file. It reuses
the PNG converter for the tileset image, so the generated symbols are exactly
the same as for a `kind = "background"` image: `const gr_tileset <name>_tileset`
and `const gr_map <name>_map`. `examples/grain-demo` imports its track from
`assets/track.tmx` this way, and its Grain source still refers to `track_tileset`
and `track_map`.

v1 supports:

- orthogonal maps with 8x8 tiles;
- tile layers encoded as CSV, XML `<tile gid="...">`, or base64 with raw, zlib
  or gzip payloads;
- one image-based tileset, inline in the `.tmx` or referenced through an
  external `.tsx` (image paths resolve relative to the `.tsx`);
- an optional `layer` name; without it, the first tile layer is imported.

Tiled GID `0` is the empty tile and maps to Gramma tile index `0`. Other GIDs
are offset by the tileset's `firstgid`, then remapped through the deduplicated
tilesheet. The layer's width/height become the `gr_map` dimensions. Manifest
entries use `kind: "map"` and include `layer`, `firstgid`, `map_width`,
`map_height`, `tile_count`, `unique_tiles`, `bpp`, `packing`, `palette_colors`,
`rom_bytes` and `source`.

The importer rejects features it cannot represent faithfully: infinite maps,
non-8x8 tiles, multiple tilesets, flipped/rotated GIDs, object/image/group
layers, tile animations, malformed or too-short layers, and GIDs outside the
tileset. CPU-side tile flipping, animated tiles and multi-layer compositing are
not part of v1. `[target.<name>.map.<asset>]` accepts `bpp`, `layer`,
`chr_bank`, `chr_tile` and `skip`; maps are placed like other backgrounds in
NES CHR and use `#pragma bank 1` on Game Boy.

### NES CHR layout

`generate()` emits an 8 KB-per-bank `nes_chr_data` object for the NES. The bank
count comes from `[mapper.nes]` (`chr_banks = 1, 2, 4 ... 16` for mmc1/mmc3;
nrom stays at 1), and the build driver enlarges the cc65 `ROM2` segment to
match. The bytes are written as `chr.s` into that segment instead of a C array,
because cc65 rejects arrays over 64 KB; C tilesets still reference
`extern const uint8_t nes_chr_data[]`. Each 8 KB bank holds one 4 KB tile table
followed by an identical copy. Both PPU pattern tables therefore contain the
same tiles, so fetches do not depend on PPUCTRL's pattern-table bits.

Images and Tiled maps can be pinned to a bank and local tile index:

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

Generated GB image, map and audio C files start with `#pragma bank 1`. Keeping large
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
emitted `gr_sfx_def` uses `GR_WAVE_PCM`; PC plays those samples directly, while
GB and SMS approximate them with tones. On `nes` only, the same source WAV is
also encoded as a 4-bit DMC sample: `process_audio()` emits a `gr_dmc`
descriptor in the generated C and a 64-byte-aligned `*_dmc.s` in the linker's
`DMC` segment. `dmc_rate` selects the APU rate index (0 ~ 4.2 kHz .. 15 ~ 33 kHz)
and `dmc_loop` sets the loop bit; an invalid rate is a structured
`budget.dmc_rate` error. Non-NES targets emit neither the descriptor nor the
sample symbol, so the portable C file stays linkable everywhere. The manifest
records `dmc_bytes`/`dmc_rate` for audio assets and includes DMC bytes in the
NES ROM byte total; GB/PC/SMS always report `dmc_bytes: 0`. SFX share the PSG
with music on SMS/GG; generated `[[music]]` songs use a PSGlib-format stream
(see below).

## Music (tracker scores)

`[[music]]` compiles a plain-text score into `const gr_song <name>` in
`generated/<target>/<name>.c`. The same generated symbol can be referenced from
C (`extern const gr_song theme;`) or Grain (`extern song theme`). Hand-written
`gr_song` values remain valid: the generated structure's new trailing `psg`
member defaults to `NULL` when a C initializer lists only the original fields.

A score uses one row per 16th-note tick. Directives start with a keyword; `;`
starts a comment, and `#` does so only at the start of a token so `C#4` works:

| Directive | Meaning |
|---|---|
| `bpm <n>` | tempo, 1..65535 (default 120) |
| `fps <n>` | console frames per second for PSG timing, 1..255 (default 50) |
| `channels <n>` | cells per row, 1..4 (default 1); must precede all patterns |
| `wave <name>` | `square`, `triangle`, `saw` or `noise` for portable notes (default `square`) |
| `loop` / `loop on` / `loop off` | looping, on by default |
| `pattern <name>` | starts a named pattern; its indented rows follow |
| `order <name>...` | pattern play order; may repeat names |

Each row has exactly `channels` whitespace-separated cells:

- `-` holds the current note on that channel;
- `off` cuts it (a rest);
- `NOTE:VOL` triggers a note at volume 0..15, e.g. `C4:11`, `F#5:7`, `Db3:9`.
  Notes use scientific pitch notation from `C0` to `B8` (`A4` = 440 Hz).

Example (`assets/theme.tick`):

```text
bpm 160
fps 50
channels 2
wave square

pattern a
    C5:11 C3:13
    -     -
    G5:11 -
    off   off

order a a
```

The compiler emits two representations from one score:

- A portable `gr_note` event stream (lead channel 0, RLE durations in ticks,
  `fps`-independent) for PC, GB and NES. Those backends keep their existing
  one-note-at-a-time sequencer, so v1 polyphony is limited to the PSG stream.
- An **uncompressed PSGlib-format byte stream** for `sms` (also used by the
  `--gg` build): `0x01` loop marker, SN76489 latch (`1cc t xxxx`) and data
  (`01xx xxxx`) pairs for channels 0-2 tone / 3 noise, `0x38|extra` frame waits
  (1-8 frames) and a final `0x00`. Compressed PSG markers `0x08-0x37` are never
  emitted and the SMS player stops if it encounters one. One row lasts
  `max(1, round(fps * 15 / bpm))` frames.

`[target.<name>.music.<asset>]` supports `skip = true` to omit a score for one
target. Generated music files use `#pragma bank 1` on Game Boy, like images and
SFX. The manifest records `kind: "music"` with `notes`, `psg_bytes` and `frames`.

## Budget linter

`gr check --target <name>` validates:

- bpp support and palette size for every image and map,
- nametable tile limit for backgrounds and maps (960 tiles for a single NES
  nametable),
- total unique tiles against VRAM,
- live sprite count and per-scanline limit,
- generated asset bytes against the ROM limit,
- NES mapper ID, mirroring mode (four-screen only on NROM), power-of-two PRG
  count (2..16 on MMC1/MMC3, 2 on NROM), power-of-two CHR count (up to 16),
  per-image bank/tile ranges, the 256-tile capacity of each CHR bank, and a
  `dmc_rate` in 0..15. Generated DMC bytes count toward the NES ROM budget.
- Game Boy mapper ID, power-of-two ROM/SRAM bank counts and per-mapper caps.
- SMS power-of-two ROM bank count (2..64), the ROM-size header code and that the
  declared layout fits `budgets.sms.rom_kb`.

Errors are printed with `error:` prefixes and fail the build. This is a core
feature: hardware limits are enforced before a ROM is ever flashed.
