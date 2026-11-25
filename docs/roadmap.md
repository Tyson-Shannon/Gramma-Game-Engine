# Roadmap status

Against `Gramma_Engine___Technical_Plan.md`:

## Done

- Monorepo skeleton: `core/`, `targets/`, `tools/gr/`, `pipeline/`,
  `examples/test-kart/`, `docs/`, `tests/`.
- Portable C99 API: fixed-point math, static actor pool, scenes, sprites,
  backgrounds, palettes, canonical input, music/SFX, frame lifecycle.
- PC simulator backend: SDL2 window, software tile renderer, keyboard/gamepad,
  four-channel synthesized audio, headless test mode and frame dumps.
- Game Boy / GBC backend: GBDK-2020 build producing a valid 32 KB `.gb` ROM
  from the same game source; verified in a headless emulator.
- NES backend: cc65 build producing a valid `.nes` ROM from the same game
  source. One fixed 32 KB PRG layout, mirrored 8 KB CHR banks (one by default,
  more on MMC1/MMC3), one nametable, 8x8 sprites, serial two-player input, APU
  music/SFX, coarse and fine scrolling; verified with `nes-py` (sprites,
  movement and sub-tile
  background shifts). A custom NMI in `targets/nes/src/nes_crt0.s` replaces the
  cc65 handler so `$2005` is not reset every vblank.
- Banking abstraction foundation: opt-in `gramma/bank.h` with cached bank sets
  and backend writers, plus `gramma/target/nes/mapper.h` with an NROM mapper
  state. The NES backend initialises zero switchable PRG/CHR slots; unsupported
  mappers fail explicitly. See [`banking.md`](banking.md).
- MMC1/MMC3 register writers: MMC1 serial PRG/CHR banking and MMC3 R0-R7 bank
  writes are implemented behind the NES mapper extension and covered by C unit
  tests. `[mapper.nes]` in `project.toml` is parsed and validated by the budget
  linter.
- Mapper-aware NES ROM generation: the build driver emits the configured
  mapper's iNES header and ca65 defines; the custom crt0 programs mapper
  registers at startup. NROM, MMC1 and MMC3 ROMs all build and pass the same
  `nes-py` smoke test. See [`banking.md`](banking.md).
- Larger NES CHR layouts: MMC1/MMC3 CHR ROM can be 1, 2, 4 ... 16 banks of
  8 KB, with per-asset `chr_bank`/`chr_tile` placement inside each mirrored
  4 KB table. CHR data is emitted in assembly so cc65 can build the full
  128 KB, and a NES 2.0 header covers layouts above 15 banks. Generated
  two-bank and 16-bank MMC3 ROMs pass `nes-py`; the two-bank ROM switches to
  distinct sprite tiles and restores the original frame exactly.
- Shipped two-bank example: `test-kart` now includes `assets/altkart.png`,
  defaults to MMC3/two CHR banks, and toggles CHR slot 2 with B through the
  generic `gr_bank_switch` helper. The shipped ROM itself demonstrates bank
  switching; no temporary ROM patching is needed.
- Larger NES PRG layouts: MMC1/MMC3 support 2, 4, 8 ... 16 banks of 16 KB.
  Code stays in the final two banks, earlier banks are data-only, and a
  RAM-resident `gr_nes_prg_read()` copies bytes from them. A four-bank MMC3
  ROM renders and switches CHR correctly in `nes-py`. The overlay queue links
  into a second code segment so `ROMFIX` still fits in 16 KB.
- Game Boy MBC bank sets: MBC1/MBC3/MBC5 expose one 16 KB ROM window and an
  optional 8 KB SRAM window. `[mapper.gb]` drives GBDK cart flags, and the
  shipped MBC1 ROM probes a bank-2 sentinel through a `BANKED` helper.
- Vblank overlays: the opt-in `gramma/overlay.h` queue stages tile and
  nametable patches immediately and applies them from the backend's vblank
  handler. GB and SMS upload sprite tiles and a small map patch; NES budgets 64
  nametable writes and uses CHR bank switches for tile changes.
- SMS/Game Gear backend: SDCC 4.5.0 + pinned devkitSMS produce bootable `.sms`
  and `.gg` ROMs from the same game source. It implements the 256x192 VDP
  nametable, 4bpp planar tiles, 16-color CRAM conversion, two joypads, simple
  SN76489 tones, Sega slot-2 banking and vblank overlays. CI checks the SEGA
  header, region/size byte, checksum and bank sentinels; rendered emulator and
  hardware checks are still pending.
- Asset pipeline v0: PNG -> deduplicated tiles (chunky and planar), RGB555
  palettes, tile maps; WAV -> PCM SFX; per-target asset overrides.
- Budget linter v0: ROM, VRAM, palette, sprite and nametable checks.
- `gr` CLI: `new`, `assets`, `grain`/`transpile`, `check`, `build`, `run`,
  `clean`, `targets`, `doctor`, with zero-sudo toolchain bootstrapping.
- Grain language v1 (Phase 3): lexer, brace-delimited recursive-descent parser,
  static typechecker with source locations, and an AOT C89 transpiler that emits
  entity pools, scenes, handlers, `gr_config` and `main()` against the portable
  API. v1 adds typed locals (`var`), typed user functions (`func ... ->`), fixed
  arrays (`T[N]`, `[...]`, `a[i]`) and C89 declaration hoisting. Integrated into
  `generate()`/`gr build`; `gr grain --check` reports diagnostics and
  `examples/grain-demo/` builds one Grain game for PC, GB, NES and SMS/GG. No
  runtime interpreter ships. A thin VS Code extension highlights `.grain` files
  and surfaces `--check` diagnostics. See [`grain.md`](grain.md).
- Example "test-kart": scrolling background, animated two-player sprites,
  music and SFX from one source tree.
- Tests: C fixed-point, bank-abstraction, GB/SMS mapper and overlay unit tests,
  Python pipeline/budget/mapper/Grain tests (including a Node smoke test of the
  VS Code diagnostics adapter), headless simulator smoke test, GB/NES/SMS ROM
  structure checks and PyBoy/`nes-py` emulator smoke tests in CI for rendering,
  sprites, scrolling and banked art. SMS/GG CI verifies ROM structure because no
  maintained headless SMS emulator is available in the CI image.

## Not done (from the plan)

- **Phase 0 hardware notes**: hand-written NES/Genesis demo programs from the
  plan were not created; the shared `test-kart` example exercises both targets.
- **Additional backends**: Genesis, GBA and SNES. Budget profiles and target
  selection hooks are in place, but no backend code. SMS/GG is implemented and
  structurally verified.
- **NES depth**: NROM, MMC1 and MMC3 ROM headers, startup programming, C-side
  runtime bank switching, larger CHR layouts and larger PRG layouts all work.
  Split palettes/nametables, DMC samples and physical hardware testing remain
  out of scope. Fine scrolling works via the custom NMI.
- **Physical hardware (deferred)**: GB and NES are verified in emulators only.
  The manual checklist in [`hardware-validation.md`](hardware-validation.md)
  covers MBC bank probes, GB overlays and NES CHR/PRG bank behavior, but is
  skipped for now. Emulator CI remains the verification gate; skipped is not
  recorded as passed.
- Tiled `.tmx` import, tracker music compiler, more per-target extension
  headers, Docker toolchain images, a full Grain language server (completion,
  rename, refactoring), performance guides and community beta.
- CI matrix covers PC, GB and NES builds plus emulator smokes, and SMS/GG builds
  plus structural ROM checks, not six toolchains. It also checks Grain sources
  and builds `examples/grain-demo/` for all four targets. SMS rendered-frame
  emulation and physical hardware runs remain manual or future work by design.

## Next steps

Physical hardware validation is deferred and is not a blocker for software work.
The checklist in [`hardware-validation.md`](hardware-validation.md) stays pending
and must be run later with an MBC1-capable GB/GBC cart and an MMC3-capable NES
cart; emulator passes are not recorded as hardware results.

1. **SMS/GG runtime validation:** add a maintained headless SMS emulator or a
   manual emulator pass that confirms rendered frames, the B overlay and the
   bank-2 probe. Keep structural ROM checks as the CI gate until then.
2. **Phase 3 tooling:** add a tracker music compiler (including PSGlib output
   for SMS/GG), Tiled `.tmx` import and Docker toolchain images. A full Grain
   language server can build on the thin VS Code CLI adapter if completion,
   rename and refactoring are wanted. Revisit the CI matrix once more
   toolchains are available.
3. **Physical hardware (later):** when hardware and carts are available, run the
   manual checklist, record date/tester/hardware/ROM hash/result in its results
   table, and summarise the outcome in [`progress.md`](progress.md).

See [`progress.md`](progress.md) for the chronological change log.
