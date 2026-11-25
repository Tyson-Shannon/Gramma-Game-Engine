# Architecture

```
 game sources (.c / .grain) + project.toml + source assets
                         |
                     gr CLI
        +----------------+----------------+----------------+
        | Grain compiler | asset pipeline | budget linter | build driver
        +----------------+----------------+----------------+
                         |
      generated C + NES CHR assembly + meson / lcc / cl65 / sdcc
                         |
              portable core (gramma_core)
                         |
       +---------+---------+---------+---------+
       |         |         |         |         |
   targets/pc targets/gb targets/nes targets/sms  (future Genesis/GBA/SNES)
   SDL2 soft   GBDK-2020  cc65/NROM/  SDCC + devkitSMS
   renderer               MMC1/MMC3
```

The Grain compiler is host-only: it parses and typechecks `.grain` sources and
emits C89 into the same generated directory as converted assets. v1 locals,
user functions and fixed arrays are lowered to C89 constructs before output;
there is still no runtime component in `core/` and generated entity/scene
handlers call the portable API exactly as hand-written C does. A thin
[VS Code extension](../editors/vscode-grain/) runs `gr grain --check` for
diagnostics but is not part of the build. See [`grain.md`](grain.md).

The core owns the frame loop, actor pool, scene pointer, input/audio/palette
dispatch, fixed-point math, the cached bank-set layer and the optional vblank
overlay queue. A backend implements the internal `gr_backend` interface in
[`core/include/gramma/internal/backend.h`](../core/include/gramma/internal/backend.h):
init/quit, frame begin/draw/end, pad state, palette load, music/SFX, ticks,
overlay apply and quit request. `gr_init` selects the backend at compile time via
`GRAMMA_TARGET_*`; there is no runtime detection and no dynamic linking.

Staging an overlay copies source bytes into a small work-RAM queue immediately;
the backend applies them from its frame-end handler. GB uploads tiles and map
patches after `wait_vbl_done()`, while NES rewrites nametable bytes within its
custom NMI budget and uses CHR bank switches for tile art. This keeps banked
source data from being read after the mapper window has been restored.

Rendering data is deliberately tile-based. The asset pipeline emits deduplicated
8x8 tiles, RGB555 palettes and tile maps. The PC backend rasterizes those exact
arrays into an RGB565 framebuffer; the GB backend uploads them to VRAM with
`set_bkg_data`/`set_sprite_data`; the NES backend links generated CHR into
CHR-ROM and never writes the pattern tables at runtime. This keeps the
simulator honest: it exercises the same data a console will consume.

Opt-in extension headers live under `gramma/target/<name>/`. The NES and Game
Boy mapper headers build on the generic bank-set API in
[`gramma/bank.h`](../core/include/gramma/bank.h); the overlay queue is another
opt-in header, [`gramma/overlay.h`](../core/include/gramma/overlay.h). The base
API intentionally exposes portable *access patterns*, while extensions expose
hardware features without polluting `gramma.h`. See [`banking.md`](banking.md).

## Build drivers

- **PC:** `gr` runs the pipeline, then Meson/Ninja. SDL2 is discovered via
  pkg-config; on Ubuntu without dev headers, `gr` extracts `libsdl2-dev` into
  `~/.cache/gramma` and passes its include/library paths as Meson options.
- **Game Boy:** `gr` runs the pipeline, then invokes GBDK-2020's `lcc` over
  core + backend + game + generated C files, producing a `.gb` ROM. GBDK is
  downloaded into `~/.cache/gramma/tools` on first use. Generated art/audio C
  files carry `#pragma bank 1` so fixed-code banked-call helpers stay below
  `$4000`; `[mapper.gb]` adds the cart-type, ROM-bank and SRAM-bank flags.
- **NES:** `gr` runs the pipeline, then invokes cc65's `cl65` over core +
  backend + game + generated C/assembly, producing a `.nes` ROM. cc65 is
  downloaded into `~/.cache/gramma/tools` on first use. The stock `nes.cfg` is
  used for the 32 KB PRG / 8 KB CHR default; larger layouts get a generated
  config with data-only `PRG*` segments, a `CODE2` segment for `overlay.c` in
  the switchable bank, and a `RAMCODE` copy in RAM.
  `targets/nes/src/nes_crt0.s` provides the startup code and a custom NMI: it
  flushes the runtime's buffered PPU writes, resets `$2006`, and writes Gramma's
  fine-scroll bytes to `$2005`. The backend waits on the `$70` VBLANK flag that
  this NMI sets, so one game frame runs per vblank.

CI runs the Python/Meson tests, the headless PC frame dump, ROM header checks
and PyBoy/`nes-py` emulator smokes for the shipped GB and NES layouts. Real
hardware remains a manual step recorded in
[`hardware-validation.md`](hardware-validation.md).
