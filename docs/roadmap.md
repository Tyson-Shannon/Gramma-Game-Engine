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
  more on MMC1/MMC3), selectable nametables with configurable mirroring and
  split background palettes, 8x8 sprites, serial two-player input, APU
  music/tones and DMC samples, coarse and fine scrolling; verified with
  `nes-py` (sprites, movement and sub-tile background shifts). A custom NMI in
  `targets/nes/src/nes_crt0.s` replaces the cc65 handler so `$2005` is not reset
  every vblank and the `$2000` nametable shadow is restored.
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
- NES depth: `[mapper.nes] mirroring` and `gr check/build/run --mirroring`
  select horizontal, vertical or four-screen nametable layout; four-screen is
  validated as NROM-only, and MMC1/MMC3 startup writes the matching register
  bits. `gr_bg_set_nametable()` plus `gr_bg_set_palette_map()` choose the
  nametable and pack per-tile palettes into attribute bytes, with the portable
  `gr_bg_attribute()` helper covered by C tests. WAV SFX also encode to a
  64-byte-aligned 4-bit DMC sample in a `DMC` ROM segment, played through the
  APU with a configurable rate/loop. Header-byte checks (`0x42` horizontal MMC3,
  `0x43` vertical MMC3, `0x0a` four-screen NROM), the same `nes-py` boot/smoke and
  Python conformance tests pass; physical hardware and a dedicated visual demo
  remain pending. See [`targets.md`](targets.md#nes-notes) and
  [`asset-pipeline.md`](asset-pipeline.md#audio).
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
- Tracker music compiler v1 (Phase 3): `[[music]]` text scores compile to
  `const gr_song` with portable `gr_note` events plus an uncompressed
  PSGlib-format stream for SMS/GG. The SMS/GG backend interprets that stream
  with a tiny in-engine player; `test-kart` ships a generated theme. See
  [`asset-pipeline.md`](asset-pipeline.md#music-tracker-scores).
- Tiled map import v1 (Phase 3): `[[map]]` converts one orthogonal 8x8 tile
  layer from CSV/XML/base64 `.tmx` files, with inline or external image
  tilesets, into the same `gr_tileset`/`gr_map` symbols as PNG backgrounds.
  `examples/grain-demo` imports its track from Tiled. See
  [`asset-pipeline.md`](asset-pipeline.md#tiled-maps).
- Budget linter v0: ROM, VRAM, palette, sprite and nametable checks.
- `gr` CLI: `new` (`c`, `grain`, `grain-music` templates), `docs`, `lsp`,
  `assets`, `grain`/`transpile`, `check`, `build`, `run`, `clean`, `targets`,
  `doctor`, with zero-sudo toolchain bootstrapping.
- Grain language v1 (Phase 3): lexer, brace-delimited recursive-descent parser,
  static typechecker with source locations, and an AOT C89 transpiler that emits
  entity pools, scenes, handlers, `gr_config` and `main()` against the portable
  API. v1 adds typed locals (`var`), typed user functions (`func ... ->`), fixed
  arrays (`T[N]`, `[...]`, `a[i]`) and C89 declaration hoisting. Integrated into
  `generate()`/`gr build`; `gr grain --check` reports diagnostics and
  `examples/grain-demo/` builds one Grain game for PC, GB, NES and SMS/GG. No
  runtime interpreter ships. See [`grain.md`](grain.md).
- Starter templates and generated API docs (Phase 3): `gr new --template` writes
  playable `c`, `grain` and `grain-music` projects with their own assets, README
  and per-target instructions. `gr docs` emits `docs/generated/api-reference.md`
  from the public headers, and CI runs `gr docs --check`; the narrative
  [`api.md`](api.md) stays hand-written.
- Pinned Docker toolchain definitions (Phase 3): [`docker/`](../docker/) has one
  multi-stage `Dockerfile` with checksummed GBDK 4.6.0, cc65 2.19, SDCC 4.5.0 and
  devkitSMS `561bc2cb` downloads, plus a build helper and README. Static tests
  verify the pins and discovery environment. Images were not built here and
  hosted CI still installs tools on the runner.
- Grain language server v1 (Phase 3): `gr lsp` is a dependency-free stdio
  JSON-RPC server with diagnostics, completion, go-to-definition, hover,
  document symbols and single-file rename. The VS Code extension uses a small
  local client and keeps the `gr grain --check` adapter as a fallback. There is
  no cross-file workspace refactor.
- More opt-in target headers (Phase 3): `gramma/target/{gb,nes,sms}/system.h`
  export capability constants and `gr_*_system_query()`. They live outside
  `gramma.h`, fail with `GR_ERR_UNSUPPORTED` on the wrong target, and are covered
  by C89 compile checks, C unit tests and the generated API reference.
- Host-side backend contract v1: `gr serve` implements versioned JSON-RPC 2.0
  over NDJSON for project, asset, Grain, check, build/run, target, doctor and
  docs operations. `project.toml` and `manifest.json` carry schema versions,
  budget violations and Grain diagnostics are structured, and [`schemas/`](../schemas/)
  plus contract tests in `tests/test_backend_contract.py` document the stable
  boundary for a future GUI. See [`gui-frontend.md`](gui-frontend.md).
- Example "test-kart": scrolling background, animated two-player sprites,
  music and SFX from one source tree.
- Tests: C fixed-point, bank-abstraction, GB/SMS mapper, NES depth helper,
  overlay and target system unit tests, Python pipeline/budget/mapper/NES
  depth/Grain/template/API-doc/Docker/LSP tests (including a Node smoke test of
  the VS Code adapter and LSP framing),
  headless simulator smoke test, GB/NES/SMS ROM
  structure checks and PyBoy/`nes-py` emulator smoke tests in CI for rendering,
  sprites, scrolling and banked art. SMS/GG CI verifies ROM structure because no
  maintained headless SMS emulator is available in the CI image.

## Not done (from the plan)

- **Phase 0 hardware notes**: hand-written NES/Genesis demo programs from the
  plan were not created; the shared `test-kart` example exercises both targets.
- **Additional backends**: Genesis, GBA and SNES. Budget profiles and target
  selection hooks are in place, but no backend code. SMS/GG is implemented and
  structurally verified.
- **NES depth (remaining)**: mapper headers, startup programming, runtime bank
  switching, larger CHR/PRG layouts, mirroring, selectable nametables, split
  palettes and DMC playback are implemented (see Done). No dedicated ROM scene
  yet exercises all four nametables, split palettes and looping DMC audibly;
  the `nes-py` smoke covers boot, sprites, scrolling and header bits, not those
  visuals. Physical hardware testing remains deferred. Fine scrolling works via
  the custom NMI.
- **Physical hardware (deferred)**: GB and NES are verified in emulators only.
  The manual checklist in [`hardware-validation.md`](hardware-validation.md)
  covers MBC bank probes, GB overlays and NES CHR/PRG bank behavior, but is
  skipped for now. Emulator CI remains the verification gate; skipped is not
  recorded as passed.
- MOD/XM/IT importers (v1 accepts Gramma text scores), compressed PSGlib
  streams, multi-layer Tiled compositing and tile animations, cross-file Grain
  refactoring, performance guides and community beta.
- **Separate GUI frontend (planned):** a Unity/Godot-style desktop editor for
  project creation, assets, Grain/C sources, inspectors and build/run flows is
  still not implemented. The versioned host-side JSON contract now exists as
  `gr serve`; the editor must consume it rather than couple `core/`, `targets/`,
  `pipeline/` or `tools/gr/` to a GUI framework. See
  [`gui-frontend.md`](gui-frontend.md).
- CI matrix covers PC, GB and NES builds plus emulator smokes, and SMS/GG builds
  plus structural ROM checks, not six toolchains. It checks Grain sources, builds
  `examples/grain-demo/` for all four targets, verifies the generated API
  reference and runs a `grain-music` starter-project PC smoke. SMS rendered-frame
  emulation and physical hardware runs remain manual or future work by design.

## Next steps

Physical hardware validation is deferred and is not a blocker for software work.
The checklist in [`hardware-validation.md`](hardware-validation.md) stays pending
and must be run later with an MBC1-capable GB/GBC cart and an MMC3-capable NES
cart; emulator passes are not recorded as hardware results.

1. **SMS/GG runtime validation:** add a maintained headless SMS emulator or a
   manual emulator pass that confirms rendered frames, the B overlay and the
   bank-2 probe. Keep structural ROM checks as the CI gate until then.
2. **Phase 3 tooling follow-ups:** starter templates, generated API docs,
   Docker toolchain definitions, the Grain LSP and target system headers are done
   as v1. The Docker images have not been built here and hosted CI still installs
   tools on the runner; revisit the CI matrix if those images are adopted.
   Remaining ideas are MOD/XM/IT import, compressed PSGlib streams,
   multi-layer/animated Tiled maps and cross-file Grain refactoring.
3. **Physical hardware (later):** when hardware and carts are available, run the
   manual checklist, record date/tester/hardware/ROM hash/result in its results
   table, and summarise the outcome in [`progress.md`](progress.md).
4. **GUI frontend (separate track):** contract v1 is done, so choose the UI
   stack and build the editor as a client of `gr serve`, never as a dependency
   of the portable C core or pipeline. Add asset-mutation and progress methods
   behind a contract bump if the editor needs them; see
   [`gui-frontend.md`](gui-frontend.md).
5. **NES depth demo:** add a small scene that visibly switches nametables,
   mixes background palettes and plays a looping DMC sample, then extend the
   `nes-py` smoke to check those frames. Keep the physical-hardware checklist
   deferred until a cart is available.

See [`progress.md`](progress.md) for the chronological change log.
