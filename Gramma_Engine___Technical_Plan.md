# Gramma — Technical Plan

**A universal retro/console game engine for homebrew development**

Version 0.1 — Draft

---

## 1. Vision

Gramma lets a developer pick a retro console, write a game once, and build it for that console with a smooth, modern development experience. It is not a "write once, run everywhere" bytecode VM — old consoles are too different for that. Instead, Gramma is a **shared API + asset pipeline + build system with per-console backends**:

- Developers write against **one portable API** (sprites, backgrounds, palettes, audio, input, timers).
- Gramma **compiles native binaries** per console using each platform's proven toolchain.
- An **asset pipeline** converts the same source assets (PNG, sprite sheets, audio, maps) into each console's native formats.
- A **PC simulator backend** gives instant iteration; emulator integration handles testing and debugging on real targets.

The philosophy: *portable by default, powerful when you opt in.* The base API is the common denominator; per-console extension modules unlock hardware-specific features (mappers, extra tile modes, PCM playback) without polluting the core.

### Goals

1. One-language, one-API game development across all supported consoles.
2. Friendly entry point for newcomers (scripting layer), full power for experts (drop to C).
3. First-class asset pipeline — the biggest pain point in homebrew today.
4. Fast inner loop: build and run in the PC simulator in seconds.
5. Realistic budgets enforced early: ROM size, VRAM, sprite counts flagged at build time.

### Non-goals (v1)

- 3D consoles (PS1, N64, Saturn) — different engine problem entirely.
- Interpreted runtimes on 8-bit targets (no RAM for them).
- Cycle-accurate timing guarantees across platforms.
- Supporting the Atari 2600 at launch (pure cycle-counting; revisit later).

---

## 2. Language strategy

### 2.1 Engine core: C99

All engine internals and per-backend glue are written in C99:

- Every serious homebrew SDK is C-first: GBDK-2020, devkitSMS, SGDK, PVSnesLib, devkitARM, cc65.
- Cross-compilers for retro CPUs (cc65 for 6502/65C02/65816, SDCC for Z80) are mature for C only.
- C maps directly onto the hardware reality: banks, VRAM, registers. No hidden runtime.
- No exceptions, no RTTI, no heap requirement — works even on machines with 2 KB of RAM.

Engine rules enforced by convention and CI lint:

- Fixed-point math only (`gr_fixed` typedef; bit width varies per target).
- Static allocation; memory pools instead of malloc.
- Per-target feature flags via compile-time `#define` (`GRAMMA_TARGET_NES`, etc.), never runtime detection.
- Strict headers: the public API compiles cleanly on 8-, 16-, and 32-bit targets.

### 2.2 Scripting layer: "Grain" (transpiled)

For the friendly developer experience, Gramma ships **Grain** — a small, statically typed, GDScript-like language that **transpiles ahead-of-time to engine C calls**. No runtime interpreter is shipped to the console, so it costs zero bytes at run time.

- Scene/actor model: `entity`, `on_update(dt)`, `on_draw()`, signals.
- Compiles to the same C API expert users write by hand — nothing is second-class.
- Expert developers can write C directly against the Gramma API when they need to.

### 2.3 Developer-facing API (sketch)

```c
// Portable API — implemented identically by every backend
gr_result gr_init(const gr_config* cfg);
void     gr_quit(void);

// Actors & scenes
gr_actor* gr_actor_spawn(const gr_actor_def* def);
void      gr_scene_load(gr_scene_id id);

// Sprites & backgrounds
void gr_sprite_show(gr_sprite* s, gr_pal_slot pal, int x, int y);
void gr_bg_load(gr_bg* bg, const gr_tileset* tiles, const gr_map* map);

// Audio
void gr_music_play(const gr_song* song);
void gr_sfx_play(gr_sfx_id id, uint8_t channel);

// Input (abstracted to a canonical pad)
bool gr_pad_down(gr_player p, gr_button b); // UP/DOWN/LEFT/RIGHT/A/B/START/SELECT

// Frame lifecycle
void gr_begin_frame(void);
void gr_end_frame(void); // ends with vsync-equivalent wait
```

Per-platform extensions live in opt-in headers, e.g. `gramma/target/nes/mapper.h`, `gramma/target/gba/affine.h`.

---

## 3. Architecture

```
┌─────────────────────────────────────────────┐
│ Game project                                │
│   .grain / .c sources  +  assets (PNG/WAV/  │
│   Tiled .tmx)          +  project.toml      │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│ gramma CLI ("gr")                           │
│  • build orchestrator (Meson/CMake driver)  │
│  • asset pipeline  → per-target formats     │
│  • Grain → C transpiler                     │
│  • budget linter (ROM/VRAM/sprite budgets)  │
│  • run command (emulator launcher, gdb)     │
└──┬────────┬─────────┬──────────┬─────────────┘
   │        │         │          │
┌──▼──┐ ┌──▼──┐  ┌───▼───┐  ┌───▼────┐  ┌────────┐
│ GB  │ │ NES │  │ SMS/GG│  │ Genesis│  │ GBA    │ …
│GBDK │ │cc65 │  │devkit │  │ SGDK   │  │devkit  │
│     │ │     │  │SMS    │  │        │  │ARM     │
└─────┘ └─────┘  └───────┘  └────────┘  └────────┘
        plus PC simulator backend (SDL2)
```

### 3.1 Asset pipeline

One source of truth per asset; per-target converters:

| Source | Outputs per target |
|---|---|
| PNG sprite sheet | GB 2bpp tiles + map + palette; NES CHR (1/2bpp) with nametable layout; Genesis 4bpp tiles; SNES paletted tiles; GBA 4bpp/8bpp |
| PNG background | Same, plus per-target tile-limit checks (e.g. NES nametable = 960 tiles, dedup-aware) |
| WAV / OGG | Per-target sample-rate + bit-depth conversion (DMG 4-channel pulse/wave; NES APU/DPCM; Genesis YM2612 + PSG staging; GBA direct sound) |
| Tiled `.tmx` maps | Compressed/encoded map formats per platform (RLE where hardware/bank space favors it) |
| Music | Tracker-style score format compiled to per-chip event streams |

The pipeline emits C arrays + linker artifacts, deduplicates tiles, and **fails the build with clear messages when an asset breaks the target's budget** — this is a core selling point, not an afterthought.

### 3.2 Build system

- Meson driving each platform's cross-toolchain; Docker images per toolchain so nobody hand-installs six compilers.
- `gr build --target gb`, `gr run --target nes` (builds, launches Mesen with gdb stub), etc.
- CI runs the full example-game matrix on every commit: every supported target must still compile.

### 3.3 Portability layer rules

- No dynamic linking. Everything static.
- Interrupt/VBlank handling lives in the backend; the portable API exposes safe hook points only.
- Fixed timestep logic with per-target frame rates normalized (60 Hz GB/NES/Genesis/GBA/SNES; SMS where appropriate).
- Canonical button mapping (UP/DOWN/LEFT/RIGHT/A/B/X/Y/L/R/START/SELECT) translated to whatever each pad has; games declare required buttons so unsupported pads fail loudly at build time, not silently at runtime.

---

## 4. Target consoles

Phased by toolchain maturity and what each teaches the abstraction layer:

| Phase | Console | Toolchain | CPU | Why now |
|---|---|---|---|---|
| 1 | Game Boy / GBC | GBDK-2020 | SM83 | Simplest serious target; huge homebrew scene; ideal proving ground |
| 1 | PC simulator | SDL2 | host | The development loop itself |
| 2 | NES | cc65 | 6502 | Iconic; forces the hardest constraint set (banking, 2 KB nametable RAM) early |
| 2 | Sega Master System / Game Gear | devkitSMS (SDCC) | Z80 | Builds on Z80 learnings; simpler than Genesis |
| 3 | Sega Genesis / Mega Drive | SGDK | 68000 | Roomy, excellent SDK; great showcase target |
| 3 | Game Boy Advance | devkitARM (+ Butano patterns) | ARM7TDMI | First ARM target; plenty of headroom |
| 4 | SNES | PVSnesLib | 65816 | Popular but quirky (mode-specific PPU constraints); best after the API is stable |

**Deferred:** Atari 2600 (cycle-level cult of difficulty), ZX Spectrum/Amstrad CPC (tape-era workflow), PC Engine (viable cc65 fork, later), 5th-gen and beyond.

Each phase's exit criterion: the shared example game ("test kart" — scrolling BG, animated sprites, music, SFX, two-player input) runs correctly on the real hardware or in a cycle-tested emulator.

---

## 5. Delivery plan

### Phase 0 — Research & API validation (weeks 1–6)

- Hand-write the same small demo natively on GB, NES, and Genesis using their SDKs. No engine code yet.
- Deliverables: written constraint notes per platform, draft `gramma.h` API validated against real hardware quirks.
- **Milestone: demo builds and runs on all three; API sketch survives contact with reality.**

### Phase 1 — Core + GB + PC simulator (weeks 7–16)

- `gr` CLI skeleton, Meson workspace, Docker toolchain images.
- Engine core: actors, scenes, fixed-point math, input, frame loop.
- GB backend (GBDK-2020) and PC simulator (SDL2).
- Asset pipeline v0: PNG → GB tiles/palettes, WAV → GB channels.
- Budget linter v0 (ROM size only).
- **Milestone: one example game playable on GB and PC from the same source.**

### Phase 2 — Prove portability: NES + SMS (weeks 17–26)

- NES backend (cc65) including mapper abstraction (NROM first, then MMC1/MMC3).
- SMS/GG backend (devkitSMS).
- Pipeline additions: NES CHR, SMS tile formats, per-target budget rules (VRAM, sprite-per-line limits, palette sizes).
- Banking/overlay abstraction — the hardest generalization problem; designed here.
- **Milestone: example game runs on GB, NES, SMS, PC from one source tree.**

### Phase 3 — Developer experience (weeks 27–38)

- Grain language: parser, typechecker, C transpiler, VS Code extension (syntax + diagnostics via transpiler errors).
- Genesis (SGDK) and GBA (devkitARM) backends.
- Tiled `.tmx` map support; music compilation pipeline v1.
- `gr new` templates; API docs generated from headers.
- **Milestone: a newcomer can build a playable game from template in under an hour.**

### Phase 4 — SNES + polish (weeks 39–52)

- SNES backend (PVSnesLib), including Mode-7-capable extension header design.
- Editor integrations (Tiled deep-linking), debugger UX polish, performance guide per console.
- Community beta: 5–10 external developers port toy games; fix API friction they report.
- **Milestone: v0.9 public release with docs, templates, CI, and 5+ supported targets.**

---

## 6. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Lowest-common-denominator API is painfully limiting | Devs bypass the engine | Opt-in per-target extension modules from day one; base API keeps *access patterns* portable, not feature ceilings |
| Banking/overlay logic diverges per platform | Code rot across backends | Single bank-abstraction layer designed in Phase 2, exercised by two platforms before more are added |
| Audio is wildly different per chip (APU vs PSG vs YM2612 vs DMG channels) | Music doesn't translate | Design music as compiled per-chip event streams, not a playback API; accept that arrangements are per-target artifacts |
| Toolchain maintenance burden (six SDKs) | Burnout, stale builds | Docker pinning + CI compile matrix; adopt upstream SDK releases deliberately, not automatically |
| Scope creep toward "supports everything" | Never ships | Hard non-goals list (§1); new consoles only after the current phase's milestone passes |
| Legal/IP caution | Takedowns | No console BIOS redistribution, no trademarked names in repo; targets document which user-supplied files (if any) are needed |

---

## 7. Immediate next steps

1. Set up the monorepo: `core/`, `targets/`, `tools/gr`, `pipeline/`, `examples/test-kart/`, `docs/`.
2. Stand up CI with the GB + PC Docker images.
3. Phase 0 demos: clone GBDK-2020, cc65, SGDK examples; write the shared demo on all three.
4. Freeze `gramma.h` v0 from what Phase 0 taught us.
5. Publish the repo publicly early — homebrew communities (GBDev, NESdev, SGDK Discord) are the best source of free API review.
