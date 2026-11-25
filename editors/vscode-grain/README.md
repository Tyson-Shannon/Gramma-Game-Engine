# Grain for VS Code

Syntax highlighting and editor features for Grain (`.grain`) sources. The
extension starts Gramma's `gr lsp` command, a dependency-free stdio JSON-RPC
language server, using a small local client. No npm language client or separate
runtime is installed.

## Features

- TextMate grammar and bracket/Comment configuration for `.grain`.
- Diagnostics from the same lexer, parser and typechecker as `gr grain --check`.
- Completion for externs, entities, scenes, fields, functions, locals,
  parameters, builtins and constants. Typing `.` narrows candidates to fields of
  the enclosing entity or scene.
- Go-to-definition and hover for declared names and builtins.
- Document symbols and single-file rename.

If `gr lsp` cannot be started, the extension falls back to the original
debounced `gr grain --check` adapter and still publishes `file:line:col: error:
...` problems. Neither mode transpiles or builds the project.

## Install

From the repository root:

```sh
cd editors/vscode-grain
npm install -g @vscode/vsce   # once
vsce package
code --install-extension grain-gramma-0.2.0.vsix
```

Or copy/symlink `editors/vscode-grain` into your VS Code extensions directory
for development and press F5 in the extension folder.

## Use

Open any `.grain` file inside a Gramma project (a directory with
`project.toml`). Diagnostics are refreshed on open, change and save; the other
providers are registered once the server answers `initialize`. The extension
walks up from the open file to find the project root, then walks up again to
find `tools/gr/gr` unless `grain.cliPath` is set explicitly:

```json
{
  "grain.cliPath": "/absolute/path/to/gr"
}
```

Relative paths are resolved against the workspace folder and the project root.
The same CLI path is used for `gr lsp` and for the fallback adapter.

Rename is intentionally single-file: there is no cross-file workspace index or
refactor in v1. Run the adapter/framing test with `node test.js` (or `npm test`).
