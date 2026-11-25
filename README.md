# Gramma

A universal retro/console game engine for homebrew development. Write one C
game against a portable API; Gramma compiles native binaries per target and
converts the same source assets into each console's native tile formats.

This repository contains a working **Phase 2 engine** plus the Phase 3
developer-experience tracks: **Grain v1**, a statically typed, GDScript-inspired
language with locals, user functions and fixed arrays that transpiles ahead of
time to the portable C API (no console interpreter), a **tracker music compiler**
that turns text scores into portable song data with PSGlib output for SMS/GG, a
**Tiled map importer** that turns `.tmx` tile layers into the same
`gr_map`/`gr_tileset` assets as PNG backgrounds, three **starter templates**,
a deterministic **generated API reference**, pinned **Docker toolchain
definitions**, a dependency-free **Grain language server**, and opt-in
per-target system headers.
Included are the portable core, SDL2 PC simulator, Game Boy/GBC backend
(GBDK-2020, MBC1/MBC3/MBC5), NES backend (cc65, NROM/MMC1/MMC3), SMS/Game Gear
backend (SDCC + devkitSMS, Sega slot-2 mapper), opt-in banking and vblank
overlays, asset pipeline, budget linter, `gr` CLI, a playable two-player
example game and a Grain-only example. See [docs/roadmap.md](docs/roadmap.md)
for the plan, [docs/grain.md](docs/grain.md) for the language and
[docs/progress.md](docs/progress.md) for the chronological change log.

## Quick start

Requirements: Python 3.11+, Pillow, Meson/Ninja, a C compiler and SDL2
development files. The optional emulator checks need Python 3.13+ for
`nes-py>=9` (Gymnasium/NumPy 2); CI uses Python 3.13. `gr` bootstraps SDL2
headers, GBDK-2020, cc65 and the SDCC/devkitSMS toolchain into `~/.cache/gramma`
if they are missing (Linux; no sudo needed). SMS/GG builds use SDCC 4.5.0 and a
pinned devkitSMS commit.

```sh
./tools/gr/gr doctor                    # check toolchains
./tools/gr/gr run --target pc           # build + launch the simulator
./tools/gr/gr build --target gb         # produce a real MBC1 .gb ROM
./tools/gr/gr build --target nes        # produce a real MMC3 .nes ROM
./tools/gr/gr build --target sms        # produce a real Sega mapper .sms ROM
./tools/gr/gr build --target sms --gg   # produce a Game Gear .gg ROM
./tools/gr/gr grain --check --project examples/grain-demo  # check Grain source
./tools/gr/gr new --template grain-music /tmp/my-game      # playable starter
./tools/gr/gr docs --check               # verify generated API reference
cd /tmp/my-game && gr run --target pc    # (add tools/gr to PATH for this)
```

Available `gr new` templates are `c` (portable C), `grain` (AOT Grain) and
`grain-music` (Grain plus a tracker score). Each writes its own assets, source,
README and per-target build instructions. `gr docs` regenerates
`docs/generated/api-reference.md`; `gr docs --check` fails when it is stale.
`gr lsp` starts the dependency-free language server over stdio for editors.

The PC simulator runs from `examples/test-kart` by default. Headless smoke
test (also used in CI):

```sh
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  ./tools/gr/gr run --target pc --frames 10 --scale 1
```

Set `GRAMMA_SCREENSHOT=/tmp/frame.ppm` to dump a rendered frame on frame 2.

With Python 3.13+, `pyboy` and `nes-py>=9` (the Gymnasium-based release,
compatible with NumPy 2) installed, the same emulator checks CI runs can be
reproduced locally:

```sh
python3 tests/emulator_smoke.py gb build/test-kart-gb/game.gb
python3 tests/emulator_smoke.py nes build/test-kart-nes/game.nes
python3 tests/sms_rom_check.py build/test-kart-sms/game.sms --banks 4
```

## Game Boy support

GBDK-2020 builds a bootable MBC1 ROM by default. `[mapper.gb]` in
`project.toml` selects `none`, `mbc1`, `mbc3` or `mbc5`, plus 16 KB ROM bank and
8 KB SRAM bank counts; `gr build/check/run` also accept `--gb-mapper`,
`--gb-rom-banks` and `--gb-ram-banks`. The build driver emits the cart type and
bank flags, and generated image/audio C files use `#pragma bank 1` so GBDK's
banked-call helpers stay in fixed code. The example includes a `BANKED` helper
in bank 2 that returns `0x5a`, proving real switchable ROM without patching a
temporary ROM. Pressing B stages an alternate sprite tileset and a small
nametable patch through the opt-in overlay queue; PyBoy checks the rendered
difference in CI.

Mapper and overlay headers are opt-in: include
`<gramma/target/gb/mapper.h>` and/or `<gramma/overlay.h>` only when needed.
See [docs/banking.md](docs/banking.md).

## NES support

The NES backend targets cc65 2.19: one nametable, 8x8 sprites and configurable
PRG/CHR layouts. `gr run --target nes` builds the ROM and prints an emulator
hint; `gr build --target nes` leaves it at `build/test-kart-nes/game.nes`. Set
`[mapper.nes] id` in `project.toml` to `nrom`, `mmc1` or `mmc3` to emit the
matching iNES header and startup mapper programming. MMC1/MMC3 can declare
2, 4, 8 ... 16 PRG banks of 16 KB and 1, 2, 4 ... 16 CHR banks of 8 KB (NROM
stays at 32 KB PRG / 8 KB CHR). `gr build/check/run` also accept `--mapper`,
`--prg-banks` and `--chr-banks` for one-off variants. Each CHR bank mirrors one
4 KB table so rendering does not depend on PPUCTRL selection. CHR is emitted in
assembly to build the full 128 KB, with a NES 2.0 header above 15 banks.
Images can be pinned with `chr_bank` and `chr_tile`, letting the same sprite
tile index show different generated art after a bank switch. The shipped
`test-kart` defaults to MMC3 with two CHR banks and presses B to toggle between
`kart` and `altkart`; four-bank PRG and 16-bank CHR layouts have also been
smoke-tested with `nes-py`. A custom NMI in `targets/nes/src/nes_crt0.s`
replaces the cc65 handler so `$2005` is not reset every vblank.

The configured mapper is also installed at runtime, so games can switch CHR
banks with `gr_bank_select(gr_nes_mapper_chr_banks(), slot,
GR_NES_CHR_BANK4(bank))` from `gramma/target/nes/mapper.h`. Asset banks are
8 KB; mapper registers select 4 KB halves, hence the macro.

Nametable overlays are available through `<gramma/overlay.h>`, limited to 64
PPU writes per vblank; tile art changes use CHR bank switches because CHR is
ROM. PRG switching from running MMC3 code is unsafe, so data-only banks use the
RAM-resident `gr_nes_prg_read()`. Other limits: one uniform background palette
slot and PCM SFX approximated with a tone. Physical hardware testing is deferred
for now; emulator CI is the active gate. See
[docs/hardware-validation.md](docs/hardware-validation.md) for the manual
checklist to run later. See [docs/targets.md](docs/targets.md) for the full list
and [docs/banking.md](docs/banking.md) for the mapper abstraction.

## SMS / Game Gear support

`gr build --target sms` builds a bootable 64 KB Master System ROM with SDCC and
devkitSMS; add `--gg` for a Game Gear ROM. Both use the same portable game source
and 4bpp planar art. At 256x192 the VDP nametable is 32x28 tiles: background art
occupies VRAM tiles 0-255 and sprite art 256-511. Palettes are converted to the
SMS `00BBGGRR` CRAM byte or the Game Gear 12-bit word. Two controllers are
read through SMSlib; the Master System has no dedicated START button, so button
1 is used as its alias, while Game Gear uses its real START bit. Hand-written
songs play as simple SN76489 tones; songs compiled from `[[music]]` scores carry
an uncompressed PSGlib-format stream that the engine replays on three tone
channels plus noise. Compressed PSG streams are not supported.

`[mapper.sms]` selects 2, 4, 8 ... 64 ROM banks of 16 KB. `gr check/build/run`
accept `--sms-rom-banks` for one-off layouts. Banks 0 and 1 are fixed; a Sega
mapper maps banks 2..N-1 into `$8000-$BFFF` by writing `$FFFF`. The build emits
the matching SEGA header region/size byte and compiles `bankN_*.c` sources into
`BANKN` linker segments. The shipped example probes bank 2 and stages an
alternate sprite tileset through the same opt-in overlay queue used on GB.

CI verifies the SMS/GG ROM structure: size, `TMR SEGA` header, region/size byte,
checksum and bank-2/bank-3 sentinels. There is no maintained headless SMS
emulator in the CI image, so this is the automated gate; rendered-frame and
physical-hardware checks remain future work. See
[docs/targets.md](docs/targets.md) for limits and
[docs/banking.md](docs/banking.md) for the mapper API.

## Opt-in target headers

`gramma.h` stays portable and does not include hardware-specific headers.
Banking, mapper and overlay APIs are opt-in, as are the new capability headers
`<gramma/target/gb/system.h>`, `<gramma/target/nes/system.h>` and
`<gramma/target/sms/system.h>`. Each exposes a `gr_*_system_query()` function
plus constants for that console; querying the wrong target returns
`GR_ERR_UNSUPPORTED` instead of silently reporting fake limits. See
[docs/api.md](docs/api.md#opt-in-target-system-headers) and the
[generated API reference](docs/generated/api-reference.md).

## Grain language

Write a whole game in `src/*.grain` and let `gr build` transpile it into
C89 calls against the same portable API hand-written games use. One source
builds for PC, GB, NES and SMS/GG; there is no runtime interpreter on the
console. v1 adds typed locals (`var n: int = 0`), typed user functions
(`func step(dt: fixed) -> fixed { ... }`) and fixed arrays (`int[4]`,
`[1, 2, 3, 4]`, `a[0]`) on top of the v0 declarations and handlers. The syntax is
GDScript-inspired but uses braces for blocks:

```grain
extern tileset kart_tileset

entity Kart {
    tileset: tileset = kart_tileset;
    speed: fixed = 1.5;

    on_update(dt: fixed) {
        x = fclamp(x + fmul(speed, dt), 0, itof(240));
        show(self, 0, ftoi(x), ftoi(y));
    }
}

game {
    title = "My Grain game";
    on_init() {
        spawn(Kart, itof(40), itof(80));
    }
}
```

```sh
./tools/gr/gr grain --check --project examples/grain-demo
./tools/gr/gr build --target pc --project examples/grain-demo
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  ./tools/gr/gr run --target pc --project examples/grain-demo --frames 10 --scale 1
```

`gr grain` (alias `gr transpile`) emits `generated/<target>/grain_<name>.c`
for inspection; `--check` reports `file:line:col` diagnostics without writing
anything. Add `[grain] sources = [...]` to `project.toml` or rely on automatic
`src/*.grain` discovery. The language, builtins and current limits are
documented in [docs/grain.md](docs/grain.md).

An optional VS Code extension in [`editors/vscode-grain/`](editors/vscode-grain/)
provides `.grain` syntax highlighting and starts `gr lsp`, a dependency-free
stdio JSON-RPC language server. It publishes compiler diagnostics and supports
completion, go-to-definition, hover, document symbols and single-file rename.
It keeps the original `gr grain --check` adapter as a fallback when the server
cannot start; cross-file refactoring is not in v1.

## Developer tooling

`gr docs` generates `docs/generated/api-reference.md` from the public headers,
and hosted CI runs `gr docs --check` so a header change cannot leave the
reference stale. The narrative guide stays in [docs/api.md](docs/api.md).
[`docker/`](docker/) contains a multi-stage `Dockerfile`, a build helper and a
README pinning GBDK 4.6.0, cc65 2.19, SDCC 4.5.0 and a fixed devkitSMS commit by
checksum. Those images are not built here and hosted CI still installs tools on
the runner; static tests verify the pins and documented environment.

The versioned host-side contract is implemented: `gr serve` speaks JSON-RPC
2.0 over newline-delimited JSON on stdio, with schema versions in
`project.toml`/`manifest.json` and stable diagnostic objects. GUI clients talk
to that contract so the CLI, pipeline and portable C backend remain usable on
their own; see [`docs/gui-frontend.md`](docs/gui-frontend.md) and
[`schemas/`](schemas/). A Unity/Godot-style GUI editor itself is still planned,
not implemented.

```sh
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"service.version","params":{}}' \
  | ./tools/gr/gr serve
```

## Controls (PC simulator)

| Action | Player 1 | Player 2 | Gamepad |
|---|---|---|---|
| Move | Arrow keys | W/A/S/D | D-pad / left stick |
| A | Z | J | A (south) |
| B | X | K | B (east) |
| X / Y | C / V | U / I | X / Y |
| L / R | Left Shift / Ctrl | O / P | Shoulders |
| Start / Select | Enter / Backspace | Tab / Backtick | Start / Back |

## Repository layout

```
core/                 portable C99 API, actors, scenes, fixed-point math
targets/pc/           SDL2 simulator backend (software tile renderer + synth)
targets/gb/           Game Boy / GBC backend (GBDK-2020)
targets/nes/          NES backend (cc65, NROM/MMC1/MMC3, custom NMI)
targets/sms/          SMS/Game Gear backend (SDCC + devkitSMS, VDP + PSG)
tools/gr/             `gr` CLI: new, docs, lsp, serve, assets, grain, check, build, run, doctor
pipeline/             PNG/TMX/WAV/tick -> C arrays, budget profiles, Grain compiler, API docs
examples/test-kart/   shared C example game and its source assets
examples/grain-demo/  game written entirely in Grain
editors/vscode-grain/ VS Code syntax highlighting plus the Grain LSP client
docker/               pinned multi-stage toolchain images and build helper
tests/                C unit tests, Python pipeline/Grain/LSP/template tests, emulator smokes
docs/                 API guide + generated reference, architecture, targets, pipeline, banking, grain, hardware validation, roadmap, progress, GUI contract
schemas/              JSON Schema descriptions for project, manifest and service contract
```

## Design rules

- C99, static allocation, fixed-point math, no runtime target detection.
- Portable API is implemented identically by each backend; hardware-specific
  features live in opt-in target headers.
- Assets fail the build when they break a target's ROM/VRAM/palette budget.
- Grain is compiled ahead of time into the same C API; no interpreter ships.
- No BIOS, ROMs or trademarked assets are redistributed.
