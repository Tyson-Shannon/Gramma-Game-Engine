# Separate GUI frontend (planned)

**Status: backend contract v1 is implemented; the GUI is not.** This document
describes the shipped host-side service and the future direction for a
Unity/Godot-style desktop editor. No GUI code exists yet.

## Goal

Give Gramma a graphical project editor without making the engine or its tooling
depend on a GUI framework. The editor should be a replaceable client of a
versioned backend contract, so another person can take `core/`, `targets/`,
`pipeline/` and `tools/gr/` and build a different frontend, or use only the CLI.

The canonical project remains plain files on disk: `project.toml`, source files,
source assets and generated artifacts. Opening a project in the GUI must not be
required to build it.

## Boundary

Proposed shape:

```text
GUI frontend (separate package/repo)
  project tree, inspector, asset browser, code editor, build/run panels
        |
        | versioned JSON-RPC / newline-delimited JSON, one process per app
        v
gr service (`gr serve`, implemented host-side Python)
  project CRUD, pipeline, budget checks, Grain checking/transpiling,
  build/run drivers, toolchain discovery, docs, structured diagnostics
        |
        v
pipeline/ + tools/gr/ target drivers        portable C core + console backends
  generated/<target>/manifest.json          core/ include/gramma.h
```

Rules:

- No GUI framework imports in `core/`, `targets/`, `pipeline/` or the portable
  C API. The backend stays usable from `gr`, scripts, CI and other editors.
- The GUI never imports backend Python modules, reads toolchain cache paths or
  parses human-only CLI stdout. It calls documented JSON methods.
- The existing VS Code extension and `gr lsp` remain first-class clients. The
  GUI should reuse the same language semantics rather than reimplement them.
- Long operations are jobs with progress, cancellation and structured results;
  they do not hang a UI thread behind a blocking subprocess call.

## Backend contract v1 (implemented)

`gr serve` speaks JSON-RPC 2.0 over newline-delimited JSON on stdio. CLI/build
chatter is redirected to stderr so stdout stays a clean protocol stream. The
contract version and method list are available from `service.version` and
`service.capabilities`.

Implemented methods:

- `service.version`, `service.capabilities`
- `project.create` (template `c`, `grain` or `grain-music`), `project.open`,
  `project.validate`, `project.save`
- `assets.list`, `assets.generate`
- `grain.check` returning structured
  [`GrainError.as_dict()`](../pipeline/gramma_pipeline/grain/errors.py) records,
  plus `grain.transpile`
- `check` returning structured budget violations, not only formatted text
- `build`, `run`, `targets`, `doctor`
- `docs.generate`, `docs.check`

`project.save` accepts full TOML text and validates it before replacing the
file, so a GUI can add assets without a second TOML writer. Dedicated
`assets.import`/`assets.remove` methods and streaming `progress`/`log` events
are deferred until a real editor needs them.

Supporting format work is in place:

- `[project] schema_version = 1` is written by all starter templates and both
  examples. Older projects without the field default to version 1; newer
  versions fail explicitly.
- `generated/<target>/manifest.json` has `schema_version = 1` and an
  `artifacts` object with absolute paths to the generated directory, manifest,
  `meson.build` and all generated sources.
- Diagnostics and budget violations carry `code`, `category`, `severity` and
  optional `asset` fields. JSON Schema descriptions live in
  [`schemas/`](../schemas/).

## Editor scope for v1

- New project from the three existing starter templates.
- Project tree and inspector for `[project]`, `[budgets.*]`, `[mapper.*]` and
  per-asset overrides, with backend validation before saving.
- Asset browser/importer for PNG, WAV, `.tick` scores and Tiled `.tmx` maps.
- Grain/C text editor with `gr lsp` diagnostics, completion, hover and
  go-to-definition. Visual scene/entity editing reads the Grain symbol layer;
  it does not create a second runtime representation.
- Target selector, `check`/`build`/`run` panels, structured budget reports and
  links to generated ROMs/executables.
- PC preview first; console preview uses existing emulator/ROM checks or frame
  dumps, not a new interpreter in the engine.

Explicitly out of v1: visual node scripting, a WYSIWYG tile/scene editor that
owns the source of truth, cloud projects, cross-file refactoring, new language
runtimes and any rewrite of the portable C API.

## Implementation options

- **Tauri + TypeScript (recommended candidate):** small shell, web UI, native
  file dialogs; spawns `gr serve`. Requires a Rust toolchain for packaging.
- **Electron + TypeScript:** simplest web tooling, larger distributable.
- **PySide6/Qt:** closest to the Python backend, but couples the editor to a
  specific Python GUI stack and is heavier to package portably.

The stack is an open decision. Whichever is chosen, the JSON contract is the
real boundary and should have conformance tests that do not import the GUI.

## Remaining milestones

1. ~~Define and version the service contract and structured results; add schema
   version fields to `project.toml` and `manifest.json`.~~ Done.
2. ~~Add `gr serve` as a thin adapter over existing pipeline/CLI functions, with
   contract tests using the current test-kart and Grain demo projects.~~ Done.
3. Build a minimal desktop shell that can create, open, validate, check and
   build a project through the contract only.
4. Add the editor/LSP panel, asset importer and inspector.
5. Add `assets.import`/`assets.remove` and streaming progress events if the
   desktop shell needs them; keep them behind contract version bumps.
6. Consider splitting the frontend into its own repository once the contract
   is stable, with this repository keeping the backend and compatibility tests.

## Current status

The backend half exists: `gr serve`, `schemas/` and conformance tests in
[`tests/test_backend_contract.py`](../tests/test_backend_contract.py). The
[`roadmap.md`](roadmap.md#not-done-from-the-plan) still tracks the GUI itself as
future work. The CLI and VS Code extension are unchanged clients of the same
tooling, and no GUI framework is imported by the backend.
